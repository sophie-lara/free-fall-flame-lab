"""Combustion Atlas web server: the public UI and the JSON API it uses."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import parse_qs, unquote, urlparse

from openai import OpenAIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from combustion_atlas.providers import ProviderConfig
from combustion_atlas.providers.openai_answers import OpenAIAnswerProvider
from combustion_atlas.rag.search import retrieve_conversation
from combustion_atlas.rag.store import QUARANTINE, DocumentStore

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


class HistoryTurn(BaseModel):
    """An earlier turn of the conversation, sent by the browser for follow-up questions."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(default="", max_length=4000)


class EvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1000)
    # Earlier turns (oldest first); only the last few are used, to interpret follow-ups.
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)
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
    workspace: Atlas,
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
            results = retrieve_conversation(
                store,
                request.question,
                [turn.question for turn in request.history],
                extra_queries=broad_queries(request),
                method=request.method,
                investigation=request.investigation or None,
                visible_sources=frozenset(request.include_sources),
            )
        except (ValueError, OpenAIError) as exc:
            if request.method == "keyword":
                raise
            fallback = semantic_unavailable(exc)
            results = retrieve_conversation(
                store,
                request.question,
                [turn.question for turn in request.history],
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
            payload["answer"] = provider.answer(
                request.question,
                results,
                history=[turn.model_dump() for turn in request.history],
            ).model_dump()
            payload["answered_by"] = provider.answered_by()
        except (ValueError, OpenAIError) as exc:
            refund = charged and isinstance(exc, OpenAIError)
            if refund and limiter is not None:
                limiter.refund()
            payload["answer_unavailable"] = answer_unavailable(exc, refunded=refund)
    elif charged and fallback and limiter is not None:
        limiter.refund()
    return payload


def broad_queries(request: EvidenceRequest) -> list[str]:
    """Focused extra searches for broad questions when AI answers are on (else none)."""
    from combustion_atlas.rag.search import is_broad

    if (
        not (request.generate_answer and request.allow_provider_calls)
        or request.method == "keyword"
    ):
        return []
    if not is_broad(request.question):
        return []
    from combustion_atlas.providers.openai_answers import expand_query

    return expand_query(request.question)


class PaidLimitReached(Exception):
    """A paid call was refused by the site-wide limit (HTTP 429)."""

    def __init__(self, reason: str, retry_after_s: int):
        super().__init__(reason)
        self.retry_after_s = retry_after_s


MAX_UPLOAD_BYTES = 80 * 1024 * 1024


def ingest_upload(
    workspace: Atlas,
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


class Atlas:
    """A project root: data/ with raw sources, processed files and the search index."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.data = self.root / "data"
        self.database = self.data / "embeddings/rag.sqlite3"

    def source_rows(self) -> list[dict[str, Any]]:
        """Every indexed source (reports and table files), keyed by source ID."""
        rows: dict[str, dict[str, Any]] = {}
        if self.database.is_file():
            with sqlite3.connect(self.database) as connection:
                for sid, filename, url in connection.execute(
                    "SELECT DISTINCT source_id, filename, source_url FROM chunks"
                ):
                    rows.setdefault(
                        sid, {"source_id": sid, "file_name": filename, "source_url": url}
                    )
        return list(rows.values())

    def document_path(self, source: dict[str, Any]) -> Path | None:
        """The local file whose SHA-256 starts with the source ID, under data/raw."""
        raw = (self.data / "raw").resolve()
        name = str(source["file_name"])
        for candidate in raw.rglob("*"):
            if candidate.name != name or not candidate.is_file():
                continue
            path = candidate.resolve()
            if path.is_relative_to(raw) and hashlib.sha256(
                path.read_bytes()
            ).hexdigest().startswith(str(source["source_id"])):
                return path
        return None


class AtlasHandler(BaseHTTPRequestHandler):
    workspace = Path.cwd()
    # Public hostnames accepted besides loopback, e.g. "atlas.azurewebsites.net".
    allowed_hosts: frozenset[str] = frozenset()
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
    public_dir = Path(__file__).with_name("public")

    @property
    def atlas(self) -> Atlas:
        return Atlas(self.workspace)

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
        atlas = self.atlas
        if parsed.path == "/api/health":
            self._json({"status": "ok"})
        elif parsed.path == "/api/me":
            visitor_uploads = self._visitor_uploads_enabled()
            self._json(
                {
                    "name": self._identity(),
                    "is_admin": self._is_admin(),
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
        elif parsed.path == "/api/corpus":
            from combustion_atlas.rag.corpus import corpus_summary

            if not atlas.database.is_file():
                self._json({"documents": [], "totals": {}})
                return
            with DocumentStore(atlas.database) as store:
                self._json(corpus_summary(store))
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
        if path not in {"/api/ask", "/api/uploads/approve", "/api/uploads/delete"}:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 32768 or self.headers.get_content_type() != "application/json":
                raise ValueError("A bounded JSON request is required")
            raw = self.rfile.read(length)
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
        except PaidLimitReached as exc:
            self._json(
                {"error": str(exc), "retry_after_s": exc.retry_after_s},
                HTTPStatus.TOO_MANY_REQUESTS,
            )
        except (ValueError, ValidationError) as exc:
            self._json({"error": str(exc)[:500]}, HTTPStatus.BAD_REQUEST)
        except OSError:
            self._json(
                {"error": "The request could not be completed"}, HTTPStatus.INTERNAL_SERVER_ERROR
            )
        except OpenAIError:
            self._json(
                {"error": "OpenAI request failed. Check local configuration and try again."},
                HTTPStatus.BAD_GATEWAY,
            )

    def _visitor_uploads_enabled(self) -> bool:
        return self.public_uploads and bool(self.allowed_hosts)

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
        """The public UI: index.html at "/", assets under /p/."""
        types = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".jpg": "image/jpeg",
        }
        assets = {
            "/p/app.js": "app.js",
            "/p/styles.css": "styles.css",
            "/p/logo.svg": "logo.svg",
            "/p/flame-story.js": "flame-story.js",
            "/p/flame-story.css": "flame-story.css",
            "/p/space-orbital-sunrise.jpg": "space-orbital-sunrise.jpg",
        }
        if request_path in {"/", "/index.html"}:
            target = self.public_dir / "index.html"
        elif request_path in assets:
            target = self.public_dir / assets[request_path]
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
    admins: frozenset[str] = frozenset(),
    allowed_users: frozenset[str] = frozenset(),
    paid_daily_limit: int = 0,
    paid_min_interval_s: int = 0,
    public_uploads: bool = False,
    upload_code: str = "",
    uploads_per_day: int = 3,
) -> None:
    """Serve the public UI and API. Defaults to loopback; hosted use names its hosts.

    `workspace` is the project root holding data/ (the index, raw sources, usage files).
    """
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    if host not in {"127.0.0.1", "localhost"} and not allowed_hosts:
        raise ValueError("Listening beyond loopback requires at least one allowed host name")
    handler = type(
        "Handler",
        (AtlasHandler,),
        {
            "workspace": workspace.resolve(),
            "allowed_hosts": allowed_hosts,
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
