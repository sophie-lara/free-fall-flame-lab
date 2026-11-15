"""Loopback review workspace over candidate batches and indexed document evidence."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import sqlite3
import threading
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import parse_qs, unquote, urlparse

from openai import OpenAIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from combustion_atlas.artifacts import CandidateBatch
from combustion_atlas.io import read_json
from combustion_atlas.normalization.schema import ExperimentRecord
from combustion_atlas.providers import ProviderConfig
from combustion_atlas.providers.openai_answers import OpenAIAnswerProvider
from combustion_atlas.rag.search import retrieve
from combustion_atlas.rag.store import QUARANTINE, DocumentStore
from combustion_atlas.retrieval.structured import filter_records

from .uploads import (
    VISITOR_MAX_BYTES,
    VISITOR_MAX_PAGES,
    PendingUploads,
    UploadQuota,
    approve,
    count_pages,
    delete,
    pending_for,
    quota_for,
)
from .usage import PaidCallLimiter

_WRITE_LOCK = threading.Lock()


class EvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1000)
    method: Literal["keyword", "dense", "hybrid"] = "keyword"
    investigation: str | None = Field(default=None, max_length=80)
    generate_answer: bool = False
    allow_provider_calls: bool = False
    # Quarantined uploads this browser made (their source IDs); searchable only by it.
    include_sources: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("include_sources")
    @classmethod
    def _source_ids(cls, value: list[str]) -> list[str]:
        import re as _re

        if any(not _re.fullmatch(r"[a-f0-9]{16}", item) for item in value):
            raise ValueError("include_sources must be 16-character source IDs")
        return value


def apply_paid_limit(
    request: EvidenceRequest, limiter: PaidCallLimiter | None, exempt: bool
) -> tuple[EvidenceRequest, dict[str, object] | None]:
    """Downgrade a paid request to free keyword search when the site limit is reached."""
    paid = request.generate_answer or request.method != "keyword"
    if not paid or limiter is None or exempt:
        return request, None
    decision = limiter.acquire()
    if decision.allowed:
        return request, None
    limited: dict[str, object] = {
        "reason": decision.reason,
        "retry_after_s": decision.retry_after_s,
        "remaining_today": decision.remaining_today,
    }
    return request.model_copy(update={"method": "keyword", "generate_answer": False}), limited


def ask_evidence(
    workspace: Workspace,
    request: EvidenceRequest,
    *,
    limiter: PaidCallLimiter | None = None,
    exempt: bool = False,
) -> dict[str, object]:
    if not workspace.database.is_file():
        raise ValueError("Build the document index to search evidence")
    if (
        request.method != "keyword" or request.generate_answer
    ) and not request.allow_provider_calls:
        raise ValueError("Enable OpenAI calls for semantic search or generated answers")
    from openai import OpenAIError

    from .streaming import answer_unavailable, charged_call, semantic_unavailable

    original = request
    request, limited = apply_paid_limit(request, limiter, exempt)
    charged = charged_call(original, limiter, exempt, limited)
    fallback = None
    with DocumentStore(workspace.database) as store:
        try:
            results = retrieve(
                store,
                request.question,
                method=request.method,
                investigation=request.investigation or None,
                visible_sources=frozenset(request.include_sources),
            )
        except (ValueError, OpenAIError) as exc:
            if request.method == "keyword":
                raise
            fallback = semantic_unavailable(exc)
            results = retrieve(
                store,
                request.question,
                method="keyword",
                investigation=request.investigation or None,
                visible_sources=frozenset(request.include_sources),
            )
    payload: dict[str, object] = {
        "question": request.question,
        "method": "keyword" if fallback else request.method,
        "results": results,
    }
    if fallback:
        payload["retrieval_fallback"] = fallback
    if limited:
        payload["limited"] = limited
    if request.generate_answer:
        try:
            provider = OpenAIAnswerProvider(ProviderConfig.from_environment())
            payload["answer"] = provider.answer(request.question, results).model_dump()
            payload["answered_by"] = provider.answered_by()
        except (ValueError, OpenAIError) as exc:
            refund = charged and isinstance(exc, OpenAIError)
            if refund and limiter is not None:
                limiter.refund()
            payload["answer_unavailable"] = answer_unavailable(exc, refunded=refund)
    elif charged and fallback and limiter is not None:
        limiter.refund()
    return payload


class DirectionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    topic: str = Field(min_length=3, max_length=1000)
    investigation: str | None = Field(default=None, max_length=80)
    allow_provider_calls: bool = False


class PaidLimitReached(Exception):
    """A paid call was refused by the site-wide limit (HTTP 429)."""

    def __init__(self, reason: str, retry_after_s: int):
        super().__init__(reason)
        self.retry_after_s = retry_after_s


def research_directions(
    workspace: Workspace,
    request: DirectionsRequest,
    *,
    limiter: PaidCallLimiter | None = None,
    exempt: bool = False,
) -> dict[str, object]:
    from combustion_atlas.providers.research_directions import ResearchDirectionsProvider

    if not workspace.database.is_file():
        raise ValueError("Build the document index first")
    if not request.allow_provider_calls:
        raise ValueError("Enable OpenAI calls to generate research directions")
    if limiter is not None and not exempt:
        decision = limiter.acquire()
        if not decision.allowed:
            raise PaidLimitReached(decision.reason or "AI limit reached", decision.retry_after_s)
    investigation = request.investigation or None
    with DocumentStore(workspace.database) as store:
        # Topic passages plus passages where authors discuss limitations or future work.
        primary = retrieve(store, request.topic, method="hybrid", investigation=investigation)
        forward = retrieve(
            store,
            request.topic + " future work recommendations limitations further research",
            method="hybrid",
            investigation=investigation,
            top_k=4,
        )
    seen: set[str] = set()
    results = []
    for item in [*primary, *forward]:
        if str(item["chunk_id"]) not in seen:
            seen.add(str(item["chunk_id"]))
            results.append(item)
    provider = ResearchDirectionsProvider(ProviderConfig.from_environment())
    try:
        directions = provider.directions(request.topic, results).model_dump()
    except OpenAIError:
        if limiter is not None and not exempt:
            limiter.refund()  # the provider failed after retries: not counted
        raise
    return {"topic": request.topic, "results": results, "directions": directions}


MAX_UPLOAD_BYTES = 80 * 1024 * 1024


def ingest_upload(
    workspace: Workspace,
    body: bytes,
    *,
    filename: str,
    investigation: str,
    source_url: str | None,
    embed: bool,
    folder_name: str = "raw/uploads",
) -> dict[str, object]:
    """Save an uploaded PDF under data/raw/uploads and add it without replacing the index."""
    import re

    from combustion_atlas.rag.build import add_document

    if not body.startswith(b"%PDF-"):
        raise ValueError("Upload a PDF file")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.()-]{0,78}", investigation):
        raise ValueError("Investigation ID: letters, numbers, spaces, '.', '_', '-' only")
    if source_url and not re.match(r"^https?://", source_url):
        raise ValueError("Source URL must start with http:// or https://")
    sha = hashlib.sha256(body).hexdigest()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip("-.")[:60] or "upload"
    folder = workspace.data / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{stem}.pdf"
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != sha:
        target = folder / f"{stem}-{sha[:8]}.pdf"
    if not target.exists():
        target.write_bytes(body)
    report = add_document(
        target,
        investigation_id=investigation,
        source_url=source_url or None,
        processed_dir=workspace.data / "processed/rag",
        database=workspace.database,
    )
    report["embedded_chunks"] = 0
    if embed:
        from combustion_atlas.providers import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(ProviderConfig.from_environment())
        with DocumentStore(workspace.database) as store:
            missing = [
                c
                for c in store.chunks_missing_vectors(provider.model_key)
                if c.source_id == report["source_id"]
            ]
            if missing:
                vectors = provider.embed([c.text for c in missing])
                store.append_vectors(
                    model_key=provider.model_key,
                    model=provider.model,
                    dimensions=provider.dimensions,
                    vectors={c.chunk_id: v for c, v in zip(missing, vectors, strict=True)},
                )
            report["embedded_chunks"] = len(missing)
    report["saved_as"] = target.relative_to(workspace.root).as_posix()
    return report


class ReviewNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    investigation_id: str = Field(min_length=1, max_length=80)
    test_id: str = Field(min_length=1, max_length=80)
    reviewer: str = Field(min_length=1, max_length=120)
    decision: Literal["accept_extraction", "correction_proposed", "needs_research"]
    note: str = Field(min_length=3, max_length=5000)
    evidence: str = Field(min_length=3, max_length=2000)

    @field_validator("reviewer", "note", "evidence")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Review fields require nonblank text")
        return value


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.data = self.root / "data"
        self.database = self.data / "embeddings/rag.sqlite3"

    def batches(self) -> list[CandidateBatch]:
        paths = sorted((self.data / "review").glob("*-b1-b5.json"))
        paths += sorted((self.data / "review/additional-candidates").glob("*.json"))
        return [CandidateBatch.model_validate(read_json(p)) for p in paths]

    def preserved(self) -> list[dict[str, Any]]:
        root = self.data / "review/preserved-review"
        paths = [
            root / "psi-25-b1-b5.json",
            root / "additional-candidates/flex-table13.json",
            root / "additional-candidates/saffire-ii.json",
            self.data / "review/holdout-evidence.json",
            self.data / "review/flex-table2-candidates.json",
        ]
        paths += sorted((self.data / "review/model-candidates").glob("*.json"))
        return [record for path in paths if path.is_file() for record in read_json(path)["records"]]

    def records(self) -> list[ExperimentRecord]:
        records = [r for batch in self.batches() for r in batch.records]
        keys = [(r.investigation_id, r.test_id) for r in records]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate candidate identity")
        return records

    def notes(self) -> list[dict[str, Any]]:
        path = self.data / "review/human-notes.jsonl"
        paths = [self.data / "review/preserved-review/human-notes.jsonl", path]
        notes: list[dict[str, Any]] = []
        with _WRITE_LOCK:
            for note_path in paths:
                if note_path.is_file():
                    with note_path.open(encoding="utf-8") as stream:
                        notes.extend(json.loads(line) for line in stream if line.strip())
        candidates: dict[tuple[str, str], list[str]] = {}
        for r in self.records():
            key = (r.investigation_id, r.test_id)
            canonical = json.dumps(r.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
            candidates.setdefault(key, []).append(hashlib.sha256(canonical.encode()).hexdigest())
        for preserved_record in self.preserved():
            key = (
                preserved_record["identity"]["investigation_id"],
                preserved_record["identity"]["test_id"],
            )
            canonical = json.dumps(preserved_record, sort_keys=True, separators=(",", ":"))
            candidates.setdefault(key, []).append(hashlib.sha256(canonical.encode()).hexdigest())
        for note in notes:
            note.setdefault("saved_at_utc", note.get("saved_at"))
            note_key = (str(note.get("investigation_id", "")), str(note.get("test_id", "")))
            fingerprint = note.get("candidate_fingerprint")
            note["binding_status"] = (
                "unbound"
                if not fingerprint
                else "matched"
                if fingerprint in candidates.get(note_key, [])
                else "stale"
            )
        return notes

    def save_note(self, note: ReviewNote) -> dict[str, Any]:
        if not any(
            (r.investigation_id, r.test_id) == (note.investigation_id, note.test_id)
            for r in self.records()
        ) and not any(
            (r["identity"]["investigation_id"], r["identity"]["test_id"])
            == (note.investigation_id, note.test_id)
            for r in self.preserved()
        ):
            raise ValueError("Unknown candidate")
        native = next(
            (
                r.model_dump(mode="json")
                for r in self.records()
                if (r.investigation_id, r.test_id) == (note.investigation_id, note.test_id)
            ),
            None,
        )
        preserved = next(
            (
                r
                for r in self.preserved()
                if (r["identity"]["investigation_id"], r["identity"]["test_id"])
                == (note.investigation_id, note.test_id)
            ),
            None,
        )
        if native is not None and preserved is not None:
            raise ValueError("Duplicate candidate identity; choose a distinct workspace")
        candidate = native if native is not None else preserved
        fingerprint = hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        entry = {
            **note.model_dump(),
            "saved_at_utc": datetime.now(UTC).isoformat(),
            "status": "draft",
            "candidate_fingerprint": fingerprint,
        }
        path = self.data / "review/human-notes.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK, path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {**entry, "binding_status": "matched"}

    def source_rows(self) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for record in self.preserved():
            for cell in record.get("raw_cells", []):
                p = cell["provenance"]
                sha = p.get("source_sha256")
                if sha:
                    rows.setdefault(
                        sha[:16],
                        {
                            "source_id": sha[:16],
                            "file_name": p["file"],
                            "source_url": p["source_url"],
                            "sha256": sha,
                            "investigation_ids": [record["identity"]["investigation_id"]],
                            "category": "Captured source",
                        },
                    )
        for batch in self.batches():
            s = batch.source
            rows[s.sha256[:16]] = {
                "source_id": s.sha256[:16],
                "file_name": Path(s.local_path).name,
                "source_url": s.source_url,
                "sha256": s.sha256,
                "investigation_ids": [s.investigation_id],
                "category": "Experiment table",
            }
        if self.database.is_file():
            with sqlite3.connect(self.database) as connection:
                for sid, filename, url, sha, investigation in connection.execute(
                    "SELECT DISTINCT source_id, filename, source_url, sha256, "
                    "investigation_id FROM pages"
                ):
                    row = rows.setdefault(
                        sid,
                        {
                            "source_id": sid,
                            "file_name": filename,
                            "source_url": url,
                            "sha256": sha,
                            "investigation_ids": [],
                            "category": "Indexed document",
                        },
                    )
                    if investigation and investigation not in row["investigation_ids"]:
                        row["investigation_ids"].append(investigation)
        for row in rows.values():
            row.update(provider="local", version=None, error=None, status="indexed")
            row["available_locally"] = self.document_path(row) is not None
            if row["available_locally"]:
                row["status"] = "downloaded"
        return list(rows.values())

    def document_path(self, source: dict[str, Any]) -> Path | None:
        raw = (self.data / "raw").resolve()
        name = str(source["file_name"])
        for candidate in raw.rglob("*"):
            if candidate.name != name or not candidate.is_file():
                continue
            path = candidate.resolve()
            if (
                path.is_relative_to(raw)
                and hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
            ):
                return path
        return None

    def overview(self) -> dict[str, Any]:
        records, sources = self.records(), self.source_rows()
        pages = chunks = documents = 0
        if self.database.is_file():
            with sqlite3.connect(self.database) as connection:
                pages = connection.execute("SELECT count(*) FROM pages").fetchone()[0]
                chunks = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
                documents = connection.execute(
                    "SELECT count(DISTINCT source_id) FROM pages"
                ).fetchone()[0]
        ids = sorted({i for source in sources for i in source["investigation_ids"]})
        return {
            "experiments": len(records) + len(self.preserved()),
            "human_unreviewed": len(records) + len(self.preserved()),
            "flagged": sum(bool(r.validation_messages) for r in records)
            + sum(bool(r.get("issues")) for r in self.preserved()),
            "documents": documents,
            "pages": pages,
            "chunks": chunks,
            "index_ready": self.database.is_file(),
            "demo": False,
            "files_discovered": len(sources),
            "files_failed": 0,
            "coverage": [
                {
                    "id": i,
                    "name": i,
                    "eligible": sum(i in s["investigation_ids"] for s in sources),
                    "downloaded": sum(
                        i in s["investigation_ids"] and s["available_locally"] for s in sources
                    ),
                    "failed": 0,
                }
                for i in ids
            ],
        }


class AtlasHandler(BaseHTTPRequestHandler):
    workspace = Path.cwd()
    # Public hostnames accepted besides loopback, e.g. "atlas.azurewebsites.net".
    allowed_hosts: frozenset[str] = frozenset()
    # "workspace" serves the internal review UI at "/"; "public" serves the public UI.
    ui_mode: str = "workspace"
    # Lower-case sign-in names (emails) allowed to administer a hosted deployment.
    admins: frozenset[str] = frozenset()
    # Hosted only: when set, every request except /api/health needs a signed-in identity
    # in this set (or in admins). Needed for providers like GitHub that admit any account.
    allowed_users: frozenset[str] = frozenset()
    # Site-wide paid-call limit for public deployments (None = unlimited).
    limiter: PaidCallLimiter | None = None
    # Public deployments: let visitors upload PDFs into quarantine.
    public_uploads: bool = False
    upload_code: str = ""
    uploads_per_day: int = 3
    static_dir = Path(__file__).with_name("static")
    public_dir = Path(__file__).with_name("public")

    @property
    def atlas(self) -> Workspace:
        return Workspace(self.workspace)

    def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._content(
            json.dumps(value, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def _content(
        self, payload: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _allowed_host(self) -> bool:
        host = self.headers.get("Host", "")
        port = cast(tuple[str, int], self.server.server_address)[1]
        return host in {f"127.0.0.1:{port}", f"localhost:{port}"} or host in self.allowed_hosts

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        host = self.headers.get("Host")
        if origin is None:
            return True
        # Deployed hosts sit behind an HTTPS front end; loopback stays plain HTTP.
        schemes = ("http", "https") if host in self.allowed_hosts else ("http",)
        return origin in {f"{scheme}://{host}" for scheme in schemes}

    def _identity(self) -> str | None:
        """Signed-in user name on a hosted deployment, else None.

        App Service Authentication injects X-MS-CLIENT-PRINCIPAL-NAME and strips any
        client-supplied copy. The header is only trusted when hosted (allowed_hosts
        configured); on plain loopback a client could forge it, so it is ignored.
        """
        names = self._identities()
        return names[0] if names else None

    def _identities(self) -> list[str]:
        """All names Easy Auth vouches for: the principal name, then e-mail, username
        and UPN claims from X-MS-CLIENT-PRINCIPAL (base64 JSON). Depending on the sign-in
        scopes a directory allows, the principal name can be empty while e-mail is set.
        Trusted only when hosted; App Service strips client-supplied X-MS-* headers.
        """
        if not self.allowed_hosts:
            return []
        names = [(self.headers.get("X-MS-CLIENT-PRINCIPAL-NAME") or "").strip()]
        encoded = self.headers.get("X-MS-CLIENT-PRINCIPAL") or ""
        if encoded:
            import base64

            try:
                principal = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4)))
                wanted = {
                    "email",
                    "preferred_username",
                    "upn",
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
                    "urn:github:login",
                }
                names += [
                    str(claim.get("val") or "").strip()
                    for claim in principal.get("claims", [])
                    if isinstance(claim, dict) and claim.get("typ") in wanted
                ]
            except (ValueError, TypeError, AttributeError):
                pass  # malformed header: fall back to the principal name only
        return list(dict.fromkeys(n for n in names if n))

    def _denied_by_allowlist(self) -> bool:
        """Send 403 and return True when a hosted allow-list excludes the caller."""
        if not self.allowed_hosts or not self.allowed_users:
            return False
        if urlparse(self.path).path == "/api/health":
            return False
        permitted = self.allowed_users | self.admins
        if any(name.casefold() in permitted for name in self._identities()):
            return False
        self._json(
            {"error": "This account is not on the access list for this deployment."},
            HTTPStatus.FORBIDDEN,
        )
        return True

    def _is_paid_exempt(self) -> bool:
        """Admins of a hosted deployment are not counted against the paid-call limit."""
        return bool(self.allowed_hosts) and self._is_admin()

    def _is_admin(self) -> bool:
        if not self.allowed_hosts:
            return True  # loopback-only server: the local user owns the workspace
        return any(name.casefold() in self.admins for name in self._identities())

    def _forbidden_unless_admin(self) -> bool:
        """Send 403 and return True when the caller is not an administrator."""
        if self._is_admin():
            return False
        self._json({"error": "Administrator access required"}, HTTPStatus.FORBIDDEN)
        return True

    def _analysis(self, name: str) -> Any:
        """Import an analysis module lazily; None (after a 503) when it is not installed."""
        import importlib

        try:
            return importlib.import_module(f"combustion_atlas.analysis.{name}")
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.startswith("combustion_atlas.analysis"):
                self._json({"error": "Analysis not available yet"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return None
            raise

    def do_GET(self) -> None:  # noqa: N802
        if not self._allowed_host():
            self._json({"error": "Local requests required"}, HTTPStatus.FORBIDDEN)
            return
        if self._denied_by_allowlist():
            return
        try:
            self._get()
        except (ValueError, ValidationError) as exc:
            self._json({"error": str(exc)[:500]}, HTTPStatus.BAD_REQUEST)
        except (OSError, sqlite3.Error):
            self._json(
                {"error": "Local evidence could not be read"}, HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def _get(self) -> None:
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        atlas = self.atlas
        if parsed.path == "/api/health":
            self._json({"status": "ok"})
        elif parsed.path == "/api/me":
            visitor_uploads = self._visitor_uploads_enabled()
            self._json(
                {
                    "name": self._identity(),
                    "is_admin": self._is_admin(),
                    "mode": self.ui_mode,
                    "can_upload": self._is_admin() or visitor_uploads,
                    "visitor_upload": visitor_uploads and not self._is_admin(),
                    "upload_code_required": bool(self.upload_code) and not self._is_admin(),
                    "upload_limits": {
                        "max_mb": VISITOR_MAX_BYTES // (1024 * 1024),
                        "max_pages": VISITOR_MAX_PAGES,
                        "per_day": self.uploads_per_day,
                        "remaining_today": self._upload_quota().remaining(self._visitor_key())
                        if visitor_uploads
                        else None,
                    },
                }
            )
        elif parsed.path == "/api/uploads/pending":
            if not self._forbidden_unless_admin():
                self._json({"pending": self._pending_uploads().list()})
        elif parsed.path == "/api/coverage":
            module = self._analysis("coverage")
            if module is not None:
                self._json(module.coverage_payload(atlas))
        elif parsed.path == "/api/predict/options":
            module = self._analysis("prediction")
            if module is not None:
                self._json(module.prediction_options(atlas))
        elif parsed.path == "/api/overview":
            self._json(atlas.overview())
        elif parsed.path == "/api/corpus":
            from combustion_atlas.rag.corpus import corpus_summary

            if not atlas.database.is_file():
                self._json({"documents": [], "totals": {}})
                return
            with DocumentStore(atlas.database) as store:
                self._json(corpus_summary(store))
        elif parsed.path == "/api/corpus/map":
            from combustion_atlas.providers import OpenAIEmbeddingProvider
            from combustion_atlas.rag.corpus import topic_map

            config = ProviderConfig.from_environment()
            model = config.embedding_model or "text-embedding-3-small"
            map_dimensions = (
                config.embedding_dimensions or OpenAIEmbeddingProvider._default_dimensions(model)
            )
            if not atlas.database.is_file():
                self._json({"points": []})
                return
            with DocumentStore(atlas.database) as store:
                self._json(
                    topic_map(
                        store,
                        model_key=f"openai:{model}:{map_dimensions}",
                        cache_dir=atlas.data / "processed/rag",
                    )
                )
        elif parsed.path == "/api/landscape":
            from combustion_atlas.analysis.landscape import load_cached

            landscape_path = atlas.data / "processed/rag/landscape.json"
            if not atlas.database.is_file():
                landscape = load_cached(landscape_path)
            else:
                with DocumentStore(atlas.database) as store:
                    landscape = load_cached(landscape_path, store)
            if landscape is None:
                self._json({"points": [], "clusters": [], "missing": True})
            else:
                self._json(landscape)
        elif parsed.path == "/api/limits":
            status = self.limiter.status() if self.limiter else {"enabled": False}
            self._json({**status, "exempt": self._is_paid_exempt()})
        elif parsed.path == "/api/rag-status":
            config = ProviderConfig.from_environment()
            chunks = vectors = 0
            dimensions = config.embedding_dimensions or {
                "text-embedding-3-small": 1536,
                "text-embedding-3-large": 3072,
            }.get(config.embedding_model)
            if atlas.database.is_file():
                with sqlite3.connect(atlas.database) as connection:
                    chunks = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
                    vectors = connection.execute(
                        "SELECT count(*) FROM vectors WHERE model_key = ?",
                        (f"openai:{config.embedding_model}:{dimensions}",),
                    ).fetchone()[0]
            self._json(
                {
                    "indexed_chunks": chunks,
                    "embedded_chunks": vectors,
                    "semantic_ready": chunks > 0
                    and vectors == chunks
                    and config.embedding_provider == "openai"
                    and config.openai_api_key_present,
                    "answer_ready": config.answer_provider == "openai"
                    and bool(config.answer_model)
                    and config.openai_api_key_present,
                    "embedding_model": config.embedding_model,
                    "answer_model": config.answer_model,
                }
            )
        elif parsed.path == "/api/experiments":
            batches = atlas.batches()
            self._json(
                {
                    "records": [r.model_dump(mode="json") for r in atlas.records()],
                    "preserved_records": atlas.preserved(),
                    "record_sources": {
                        f"{r.investigation_id}/{r.test_id}": {
                            **b.source.model_dump(mode="json", exclude={"local_path"}),
                            "file_name": Path(b.source.local_path).name,
                        }
                        for b in batches
                        for r in b.records
                    },
                    "mappings": [m.model_dump() for b in batches for m in b.mapping_decisions],
                    "notes": atlas.notes(),
                }
            )
        elif parsed.path == "/api/sources":
            self._json({"sources": atlas.source_rows()})
        elif parsed.path == "/api/structured-search":
            result = self._filter(query)
            self._json(
                {"records": [r.model_dump(mode="json") for r in result], "total": len(result)}
            )
        elif parsed.path == "/api/search":
            question = query.get("q", "").strip()
            k = int(query.get("k", "5"))
            if not question or len(question) > 1000 or not 1 <= k <= 20:
                raise ValueError("Enter a question and a result count from 1 to 20")
            if not atlas.database.is_file():
                self._json(
                    {"error": "Build the document index to search evidence."},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            with DocumentStore(atlas.database) as store:
                # Same keyword retrieval as Ask, so table rows named by test ID or by
                # two or more exact values are pinned here too.
                results = retrieve(
                    store,
                    question,
                    method="keyword",
                    investigation=query.get("investigation"),
                    top_k=k,
                )
            self._json({"question": question, "results": results})
        elif parsed.path.startswith("/api/documents/"):
            sid = unquote(parsed.path.removeprefix("/api/documents/"))
            source = next((s for s in atlas.source_rows() if s["source_id"] == sid), None)
            path = atlas.document_path(source) if source else None
            if path is None:
                self._json({"error": "Captured file unavailable"}, HTTPStatus.NOT_FOUND)
            else:
                self._content(
                    path.read_bytes(),
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                )
        elif parsed.path.startswith("/api/visuals/") and parsed.path.endswith("/cells"):
            from combustion_atlas.rag.tables import resolve_cells
            from combustion_atlas.rag.visual_models import VisualArtifact

            artifact_id = unquote(parsed.path.removeprefix("/api/visuals/").removesuffix("/cells"))
            row = None
            if atlas.database.is_file():
                with DocumentStore(atlas.database) as store:
                    row = store.connection.execute(
                        "SELECT payload FROM visual_artifacts WHERE artifact_id=?",
                        (artifact_id,),
                    ).fetchone()
            artifact = VisualArtifact.model_validate_json(row[0]) if row else None
            if artifact is None or artifact.table is None:
                self._json({"error": "Structured table unavailable"}, HTTPStatus.NOT_FOUND)
            else:
                self._json(
                    {
                        "artifact_id": artifact.artifact_id,
                        "label": artifact.label,
                        "caption": artifact.caption,
                        "review_status": artifact.review_status,
                        "method": artifact.method,
                        "physical_page": artifact.physical_page,
                        "table": artifact.table.model_dump(mode="json"),
                        "resolved_cells": resolve_cells(artifact.table),
                    }
                )
        elif parsed.path.startswith("/api/visuals/"):
            from combustion_atlas.rag.visual_models import VisualArtifact
            from combustion_atlas.rag.visuals import crop_file

            artifact_id = unquote(parsed.path.removeprefix("/api/visuals/"))
            if not atlas.database.is_file():
                self._json({"error": "Visual unavailable"}, HTTPStatus.NOT_FOUND)
                return
            with DocumentStore(atlas.database) as store:
                row = store.connection.execute(
                    "SELECT payload FROM visual_artifacts WHERE artifact_id=?",
                    (artifact_id,),
                ).fetchone()
            if row is None:
                self._json({"error": "Visual unavailable"}, HTTPStatus.NOT_FOUND)
            else:
                artifact = VisualArtifact.model_validate_json(row[0])
                self._content(crop_file(atlas.root, artifact).read_bytes(), "image/png")
        else:
            self._serve_static(parsed.path)

    def _filter(self, query: dict[str, str]) -> list[ExperimentRecord]:
        allowed = {
            "scope",
            "material",
            "geometry",
            "gravity_regime",
            "investigation_id",
            "oxygen_min_pct",
            "oxygen_max_pct",
            "pressure_min_kpa",
            "pressure_max_kpa",
            "airflow_min_cm_s",
            "airflow_max_cm_s",
        }
        if set(query) - allowed or query.get("scope", "candidates") != "candidates":
            raise ValueError("Use candidate scope and supported condition filters")
        ranges = {}
        for prefix in ("oxygen", "pressure", "airflow"):
            suffix = {"oxygen": "pct", "pressure": "kpa", "airflow": "cm_s"}[prefix]
            lo, hi = (
                float(query[k]) if k in query else None
                for k in (f"{prefix}_min_{suffix}", f"{prefix}_max_{suffix}")
            )
            import math

            if any(v is not None and (not math.isfinite(v) or v < 0) for v in (lo, hi)):
                raise ValueError("Ranges must be finite and nonnegative")
            if lo is not None and hi is not None and lo > hi:
                raise ValueError("Minimum must not exceed maximum")
            if prefix == "oxygen" and any(v is not None and v > 100 for v in (lo, hi)):
                raise ValueError("Oxygen must be between 0 and 100 percent")
            ranges[prefix] = (lo, hi)
        records = filter_records(
            self.atlas.records(),
            material=query.get("material"),
            geometry=query.get("geometry"),
            investigation_id=query.get("investigation_id"),
            oxygen_min_pct=ranges["oxygen"][0],
            oxygen_max_pct=ranges["oxygen"][1],
        )
        matches = []
        for record in records:
            if record.validation_status == "rejected":
                continue
            if (
                query.get("gravity_regime")
                and (record.conditions.gravity_regime or "").casefold()
                != query["gravity_regime"].casefold()
            ):
                continue
            for prefix, field, unit in (
                ("pressure", "pressure_kpa", "kPa"),
                ("airflow", "airflow_cm_s", "cm/s"),
            ):
                lo, hi = ranges[prefix]
                measure = getattr(record.conditions, field)
                if (lo is not None or hi is not None) and (
                    measure is None
                    or measure.unit != unit
                    or measure.value is None
                    or (lo is not None and measure.value < lo)
                    or (hi is not None and measure.value > hi)
                ):
                    break
            else:
                matches.append(record)
        return matches

    def do_POST(self) -> None:  # noqa: N802
        if not self._allowed_host() or not self._same_origin():
            self._json({"error": "Same-origin local requests required"}, HTTPStatus.FORBIDDEN)
            return
        if self._denied_by_allowlist():
            return
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/api/upload":
            if self._is_admin():
                self._upload(parsed_url.query)
            elif self._visitor_uploads_enabled():
                self._visitor_upload(parsed_url.query)
            else:
                self._forbidden_unless_admin()
            return
        if path == "/api/ask/stream":
            # Same host/origin checks as /api/ask (above); NDJSON progress, then the result.
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 32768 or self.headers.get_content_type() != "application/json":
                    raise ValueError("A bounded JSON request is required")
            except ValueError as exc:
                self._json({"error": str(exc)[:500]}, HTTPStatus.BAD_REQUEST)
                return
            raw = self.rfile.read(length)
            from combustion_atlas.app.streaming import stream_ask

            stream_ask(self, self.atlas, raw, limiter=self.limiter, exempt=self._is_paid_exempt())
            return
        if path not in {
            "/api/reviews",
            "/api/review-notes",
            "/api/ask",
            "/api/directions",
            "/api/predict",
            "/api/uploads/approve",
            "/api/uploads/delete",
        }:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        if (
            path in {"/api/reviews", "/api/review-notes"}
            and self.ui_mode == "public"
            and self._forbidden_unless_admin()
        ):
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 32768 or self.headers.get_content_type() != "application/json":
                raise ValueError("A bounded JSON request is required")
            raw = self.rfile.read(length)
            if path == "/api/predict":
                module = self._analysis("prediction")
                if module is not None:
                    body = json.loads(raw)
                    if not isinstance(body, dict):
                        raise ValueError("Send a JSON object with target and inputs")
                    self._json(module.predict_payload(self.atlas, body))
                return
            if path in {"/api/uploads/approve", "/api/uploads/delete"}:
                if self._forbidden_unless_admin():
                    return
                body = json.loads(raw)
                source_id = str(body.get("source_id") or "")
                entry = self._pending_uploads().pop(source_id) or {}
                try:
                    if path.endswith("approve"):
                        pages = approve(
                            self.atlas.database, source_id, str(body.get("investigation") or "")
                        )
                        self._json({"approved": source_id, "pages": pages})
                    else:
                        delete(
                            self.atlas.database, self.atlas.root, source_id, entry.get("saved_as")
                        )
                        self._json({"deleted": source_id})
                except ValueError:
                    if entry:
                        self._pending_uploads().add(entry, int(entry.get("pages", 0)))
                    raise
                return
            if path == "/api/ask":
                self._json(
                    ask_evidence(
                        self.atlas,
                        EvidenceRequest.model_validate_json(raw),
                        limiter=self.limiter,
                        exempt=self._is_paid_exempt(),
                    )
                )
                return
            if path == "/api/directions":
                self._json(
                    research_directions(
                        self.atlas,
                        DirectionsRequest.model_validate_json(raw),
                        limiter=self.limiter,
                        exempt=self._is_paid_exempt(),
                    )
                )
                return
            note = ReviewNote.model_validate_json(raw)
            self._json(self.atlas.save_note(note), HTTPStatus.CREATED)
        except PaidLimitReached as exc:
            self._json(
                {"error": str(exc), "retry_after_s": exc.retry_after_s},
                HTTPStatus.TOO_MANY_REQUESTS,
            )
        except (ValueError, ValidationError) as exc:
            self._json({"error": str(exc)[:500]}, HTTPStatus.BAD_REQUEST)
        except OSError:
            self._json(
                {"error": "Review note could not be saved"}, HTTPStatus.INTERNAL_SERVER_ERROR
            )
        except OpenAIError:
            self._json(
                {"error": "OpenAI request failed. Check local configuration and try again."},
                HTTPStatus.BAD_GATEWAY,
            )

    def _visitor_uploads_enabled(self) -> bool:
        return self.public_uploads and self.ui_mode == "public" and bool(self.allowed_hosts)

    def _visitor_key(self) -> str:
        """Who a visitor is for quotas: signed-in name, else client IP from the front end."""
        identity = self._identity()
        if identity:
            return f"user:{identity.casefold()}"
        forwarded = (
            (self.headers.get("X-Client-IP") or self.headers.get("X-Forwarded-For") or "")
            .split(",")[0]
            .strip()
        )
        if forwarded.count(":") == 1:  # "1.2.3.4:5678" -> drop the port
            forwarded = forwarded.split(":")[0]
        return f"ip:{forwarded or self.client_address[0]}"

    def _pending_uploads(self) -> PendingUploads:
        return pending_for(self.atlas.data / "uploads/pending.json")

    def _upload_quota(self) -> UploadQuota:
        return quota_for(self.atlas.data / "usage/uploads.json", self.uploads_per_day)

    def _visitor_upload(self, raw_query: str) -> None:
        """Quarantined upload: capped size/pages, optional code, per-visitor and site limits."""
        import hmac

        query = {k: v[0] for k, v in parse_qs(raw_query).items()}
        try:
            if self.upload_code and not hmac.compare_digest(
                (self.headers.get("X-Upload-Code") or "").encode(), self.upload_code.encode()
            ):
                self._json(
                    {"error": "Enter the upload code to add a document."}, HTTPStatus.FORBIDDEN
                )
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= VISITOR_MAX_BYTES:
                raise ValueError(f"Upload a PDF up to {VISITOR_MAX_BYTES // (1024 * 1024)} MB")
            if self.headers.get_content_type() != "application/pdf":
                raise ValueError("Upload a PDF file")
            visitor = self._visitor_key()
            quota = self._upload_quota()
            if quota.remaining(visitor) <= 0:
                raise PaidLimitReached(
                    f"You have used today's {quota.per_day} uploads. Try again after 00:00 UTC.",
                    0,
                )
            body = self.rfile.read(length)
            pages = count_pages(body)
            if pages > VISITOR_MAX_PAGES:
                raise ValueError(
                    f"Upload a PDF of at most {VISITOR_MAX_PAGES} pages ({pages} found)"
                )
            if self.limiter is not None:
                decision = self.limiter.acquire()
                if not decision.allowed:
                    raise PaidLimitReached(
                        (decision.reason or "Site limit reached").replace(
                            "AI answers", "AI calls (answers and uploads)"
                        ),
                        decision.retry_after_s,
                    )
            report = ingest_upload(
                self.atlas,
                body,
                filename=query.get("filename", "upload.pdf"),
                investigation=QUARANTINE,
                source_url=None,
                embed=True,
                folder_name="raw/uploads/visitors",
            )
            if report.get("status") == "added":
                self._pending_uploads().add(report, pages)
            report["quarantined"] = True
            report["uploads_left_today"] = quota.record(visitor)
            self._json(report, HTTPStatus.CREATED)
        except PaidLimitReached as exc:
            self._json(
                {"error": str(exc), "retry_after_s": exc.retry_after_s},
                HTTPStatus.TOO_MANY_REQUESTS,
            )
        except ValueError as exc:
            self._json({"error": str(exc)[:500]}, HTTPStatus.BAD_REQUEST)
        except OpenAIError:
            if self.limiter is not None:
                self.limiter.refund()
            self._json(
                {"error": "Document indexed, but semantic search setup failed. Try again later."},
                HTTPStatus.BAD_GATEWAY,
            )
        except (OSError, sqlite3.Error):
            self._json(
                {"error": "The upload could not be indexed"}, HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def _upload(self, raw_query: str) -> None:
        query = {k: v[0] for k, v in parse_qs(raw_query).items()}
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_UPLOAD_BYTES:
                raise ValueError("Upload a PDF up to 80 MB")
            if self.headers.get_content_type() != "application/pdf":
                raise ValueError("Upload a PDF file")
            body = self.rfile.read(length)
            report = ingest_upload(
                self.atlas,
                body,
                filename=query.get("filename", "upload.pdf"),
                investigation=query.get("investigation", "").strip(),
                source_url=query.get("source_url", "").strip() or None,
                embed=query.get("embed") == "1",
            )
            self._json(report, HTTPStatus.CREATED)
        except ValueError as exc:
            self._json({"error": str(exc)[:500]}, HTTPStatus.BAD_REQUEST)
        except OpenAIError:
            self._json(
                {"error": "Document indexed, but embedding failed. Retry embedding later."},
                HTTPStatus.BAD_GATEWAY,
            )
        except (OSError, sqlite3.Error):
            self._json(
                {"error": "The upload could not be indexed"}, HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def _serve_static(self, request_path: str) -> None:
        """Static assets for both UIs.

        Public UI assets live under /p/ so they never collide with the workspace UI,
        whose index.html references /app.js and /styles.css. In public mode "/" is the
        public UI and the workspace UI moves to /workspace (administrators only); in
        workspace mode "/" stays the workspace UI and the public UI previews at /public.
        """
        types = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
        }
        public_assets = {
            "/p/app.js": "app.js",
            "/p/styles.css": "styles.css",
            "/p/logo.svg": "logo.svg",
        }
        workspace_assets = {"/app.js": "app.js", "/styles.css": "styles.css"}
        if self.ui_mode == "public":
            public_pages = {"/", "/index.html"}
            workspace_pages = {"/workspace", "/workspace/"}
        else:
            public_pages = {"/public", "/public/"}
            workspace_pages = {"/", "/index.html"}
        if request_path in public_pages:
            target = self.public_dir / "index.html"
        elif request_path in public_assets:
            target = self.public_dir / public_assets[request_path]
        elif request_path in workspace_pages or request_path in workspace_assets:
            if self.ui_mode == "public" and self._forbidden_unless_admin():
                return
            name = workspace_assets.get(request_path, "index.html")
            target = self.static_dir / name
        else:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        self._content(target.read_bytes(), types.get(target.suffix, "application/octet-stream"))


def serve(
    *,
    workspace: Path,
    port: int,
    host: str = "127.0.0.1",
    allowed_hosts: frozenset[str] = frozenset(),
    ui_mode: str = "workspace",
    admins: frozenset[str] = frozenset(),
    allowed_users: frozenset[str] = frozenset(),
    paid_daily_limit: int = 0,
    paid_min_interval_s: int = 0,
    public_uploads: bool = False,
    upload_code: str = "",
    uploads_per_day: int = 3,
) -> None:
    """Serve the interface. Defaults to loopback; hosted use must name its public hosts."""
    if ui_mode not in {"workspace", "public"}:
        raise ValueError("UI mode must be 'workspace' or 'public'")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    if host not in {"127.0.0.1", "localhost"} and not allowed_hosts:
        raise ValueError("Listening beyond loopback requires at least one allowed host name")
    handler = type(
        "WorkspaceHandler",
        (AtlasHandler,),
        {
            "workspace": workspace.resolve(),
            "allowed_hosts": allowed_hosts,
            "ui_mode": ui_mode,
            "admins": frozenset(a.casefold() for a in admins),
            "allowed_users": frozenset(u.casefold() for u in allowed_users),
            "public_uploads": public_uploads,
            "upload_code": upload_code,
            "uploads_per_day": uploads_per_day,
            "limiter": (
                PaidCallLimiter(
                    workspace.resolve() / "data/usage/paid-calls.json",
                    daily_limit=paid_daily_limit,
                    min_interval_s=paid_min_interval_s,
                )
                if paid_daily_limit or paid_min_interval_s
                else None
            ),
        },
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Combustion Atlas: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
