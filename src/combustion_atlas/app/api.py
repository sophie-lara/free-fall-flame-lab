"""FastAPI application: the public UI (built React files) and the JSON API it uses.

Security rules (host and origin checks, hosted identity from App Service
Authentication, administrator and allow-list checks, paid-call and upload limits) are
the same as the previous standard-library server, so the browser contract is unchanged.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import mimetypes
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from openai import OpenAIError
from pydantic import ValidationError
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from combustion_atlas.providers import ProviderConfig
from combustion_atlas.rag.store import QUARANTINE, DocumentStore

from .core import (
    MAX_UPLOAD_BYTES,
    Atlas,
    EvidenceRequest,
    PaidLimitReached,
    ask_evidence,
    ingest_upload,
)
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

LOG = logging.getLogger("combustion_atlas.app")
JSON_BODY_LIMIT = 32768
# Responses that must reach the browser line by line (never buffered by compression).
STREAMING_PATHS = frozenset({"/api/ask/stream"})
IDENTITY_CLAIMS = frozenset(
    {
        "email",
        "preferred_username",
        "upn",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
        "urn:github:login",
    }
)


@dataclass(frozen=True)
class Settings:
    """Deployment settings (see __main__ for the matching flags and environment)."""

    workspace: Path
    # Public hostnames accepted besides loopback, e.g. "atlas.azurewebsites.net".
    allowed_hosts: frozenset[str] = frozenset()
    # Lower-case sign-in names allowed to administer a hosted deployment.
    admins: frozenset[str] = frozenset()
    # Hosted only: when set, every request except /api/health needs a signed-in identity
    # in this set (or in admins).
    allowed_users: frozenset[str] = frozenset()
    paid_daily_limit: int = 0
    paid_min_interval_s: int = 0
    public_uploads: bool = False
    upload_code: str = ""
    uploads_per_day: int = 3
    web_dir: Path = field(default_factory=lambda: Path(__file__).with_name("web"))
    # Local-disk directory for an index snapshot (fast reads when data is on a share).
    cache_dir: Path | None = None
    # Build cached responses in the background at startup.
    warm_caches: bool = False


def error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


class SelectiveGZip:
    """gzip for responses over 1 KB, except streams that must arrive incrementally."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=1024)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") in STREAMING_PATHS:
            await self.app(scope, receive, send)
        else:
            await self.gzip(scope, receive, send)


class ResponseCache:
    """Serialized JSON responses keyed by a signature of what they were built from."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[object, bytes]] = {}

    def get(self, name: str, key: object, build: Callable[[], object]) -> bytes:
        with self._lock:
            hit = self._entries.get(name)
        if hit is not None and hit[0] == key:
            return hit[1]
        body = json.dumps(build(), ensure_ascii=False).encode("utf-8")
        with self._lock:
            self._entries[name] = (key, body)
        return body


def tree_signature(*roots: Path) -> tuple[int, int]:
    """(newest mtime_ns, file count) under the given directories."""
    newest = count = 0
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                count += 1
                newest = max(newest, path.stat().st_mtime_ns)
    return newest, count


class AtlasService:
    """Per-app state and request-independent helpers."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.atlas = Atlas(settings.workspace, settings.cache_dir)
        self.limiter = (
            PaidCallLimiter(
                settings.workspace.resolve() / "data/usage/paid-calls.json",
                daily_limit=settings.paid_daily_limit,
                min_interval_s=settings.paid_min_interval_s,
            )
            if settings.paid_daily_limit or settings.paid_min_interval_s
            else None
        )
        self.cache = ResponseCache()
        self._coverage_key: tuple[float, tuple[int, int]] | None = None

    # ---- identity and permissions ----
    def identities(self, request: Request) -> list[str]:
        """Names App Service Authentication vouches for (trusted only when hosted).

        The principal name, then e-mail, username and UPN claims from
        X-MS-CLIENT-PRINCIPAL (base64 JSON). App Service strips client-supplied X-MS-*
        headers; on plain loopback a client could forge them, so they are ignored.
        """
        if not self.settings.allowed_hosts:
            return []
        names = [(request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME") or "").strip()]
        encoded = request.headers.get("X-MS-CLIENT-PRINCIPAL") or ""
        if encoded:
            try:
                principal = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4)))
                names += [
                    str(claim.get("val") or "").strip()
                    for claim in principal.get("claims", [])
                    if isinstance(claim, dict) and claim.get("typ") in IDENTITY_CLAIMS
                ]
            except (ValueError, TypeError, AttributeError):
                pass  # malformed header: fall back to the principal name only
        return list(dict.fromkeys(n for n in names if n))

    def identity(self, request: Request) -> str | None:
        names = self.identities(request)
        return names[0] if names else None

    def is_admin(self, request: Request) -> bool:
        if not self.settings.allowed_hosts:
            return True  # loopback-only server: the local user owns the data
        return any(name.casefold() in self.settings.admins for name in self.identities(request))

    def is_paid_exempt(self, request: Request) -> bool:
        """Admins of a hosted deployment are not counted against the paid-call limit."""
        return bool(self.settings.allowed_hosts) and self.is_admin(request)

    def visitor_uploads_enabled(self) -> bool:
        return self.settings.public_uploads and bool(self.settings.allowed_hosts)

    def visitor_key(self, request: Request) -> str:
        """Who a visitor is for quotas: signed-in name, else client IP from the front end."""
        identity = self.identity(request)
        if identity:
            return f"user:{identity.casefold()}"
        forwarded = (
            (request.headers.get("X-Client-IP") or request.headers.get("X-Forwarded-For") or "")
            .split(",")[0]
            .strip()
        )
        if forwarded.count(":") == 1:  # "1.2.3.4:5678" -> drop the port
            forwarded = forwarded.split(":")[0]
        client = request.client.host if request.client else "unknown"
        return f"ip:{forwarded or client}"

    def pending_uploads(self) -> PendingUploads:
        return pending_for(self.atlas.data / "uploads/pending.json")

    def upload_quota(self) -> UploadQuota:
        return quota_for(self.atlas.data / "usage/uploads.json", self.settings.uploads_per_day)

    # ---- cached payloads ----
    def coverage(self) -> bytes:
        import importlib

        coverage = importlib.import_module("combustion_atlas.analysis.coverage")

        # Re-scan the source tables at most once a minute; rebuild only when they change.
        now = time.monotonic()
        if self._coverage_key is None or now - self._coverage_key[0] > 60:
            signature = tree_signature(self.atlas.data / "raw/psi", self.atlas.data / "review")
            self._coverage_key = (now, signature)
        return self.cache.get(
            "coverage", self._coverage_key[1], lambda: coverage.coverage_payload(self.atlas)
        )

    def corpus(self) -> bytes:
        from combustion_atlas.rag.corpus import corpus_summary

        def build() -> object:
            if not self.atlas.database.is_file():
                return {"documents": [], "totals": {}}
            with DocumentStore(self.atlas.read_database) as store:
                return corpus_summary(store)

        return self.cache.get("corpus", self.atlas.database_signature(), build)

    def landscape(self) -> bytes:
        from combustion_atlas.analysis.landscape import load_cached

        path = self.atlas.data / "processed/rag/landscape.json"

        def build() -> object:
            if not self.atlas.database.is_file():
                landscape = load_cached(path)
            else:
                with DocumentStore(self.atlas.read_database) as store:
                    landscape = load_cached(path, store)
            return landscape or {"points": [], "clusters": [], "missing": True}

        file_key = path.stat().st_mtime_ns if path.is_file() else None
        return self.cache.get("landscape", (file_key, self.atlas.database_signature()), build)

    def warm(self) -> None:
        """Build cached responses and the vector matrix so first visitors are fast."""
        started = time.monotonic()
        for name, build in (
            ("coverage", self.coverage),
            ("corpus", self.corpus),
            ("landscape", self.landscape),
        ):
            try:
                build()
            except Exception:  # noqa: BLE001 - warming is best effort
                LOG.exception("warming %s failed", name)
        try:
            from combustion_atlas.providers import OpenAIEmbeddingProvider

            config = ProviderConfig.from_environment()
            model = config.embedding_model or "text-embedding-3-small"
            dims = config.embedding_dimensions or OpenAIEmbeddingProvider._default_dimensions(model)
            if self.atlas.database.is_file():
                with DocumentStore(self.atlas.read_database) as store:
                    store._vector_matrix(f"openai:{model}:{dims}")
        except Exception:  # noqa: BLE001
            LOG.exception("warming vectors failed")
        LOG.info("caches warmed in %.1fs", time.monotonic() - started)


def create_app(settings: Settings) -> FastAPI:
    service = AtlasService(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        if settings.warm_caches:
            threading.Thread(target=service.warm, name="warm-caches", daemon=True).start()
        yield

    app = FastAPI(
        title="Combustion Atlas", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.service = service

    # ---------------- security and headers ----------------
    def allowed_host(request: Request) -> bool:
        host = request.headers.get("host", "")
        server = request.scope.get("server") or ("", 0)
        port = server[1]
        return (
            host in {f"127.0.0.1:{port}", f"localhost:{port}"}
            or host in service.settings.allowed_hosts
        )

    def same_origin(request: Request) -> bool:
        origin = request.headers.get("origin")
        host = request.headers.get("host")
        if origin is None:
            return True
        # Deployed hosts sit behind an HTTPS front end; loopback stays plain HTTP.
        schemes = ("http", "https") if host in service.settings.allowed_hosts else ("http",)
        return origin in {f"{scheme}://{host}" for scheme in schemes}

    def denied_by_allowlist(request: Request) -> bool:
        if not service.settings.allowed_hosts or not service.settings.allowed_users:
            return False
        if request.url.path == "/api/health":
            return False
        permitted = service.settings.allowed_users | service.settings.admins
        return not any(name.casefold() in permitted for name in service.identities(request))

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method == "POST":
            if not allowed_host(request) or not same_origin(request):
                return error("Same-origin local requests required", 403)
        elif not allowed_host(request):
            return error("Local requests required", 403)
        if denied_by_allowlist(request):
            return error("This account is not on the access list for this deployment.", 403)
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    app.add_middleware(SelectiveGZip)

    def admin_required(request: Request) -> JSONResponse | None:
        return None if service.is_admin(request) else error("Administrator access required", 403)

    async def bounded_json(request: Request) -> bytes:
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            length = 0
        content_type = (request.headers.get("content-type") or "").split(";")[0].strip()
        if not 0 < length <= JSON_BODY_LIMIT or content_type != "application/json":
            raise ValueError("A bounded JSON request is required")
        return await read_limited(request, JSON_BODY_LIMIT)

    async def read_limited(request: Request, limit: int) -> bytes:
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise ValueError("Request body is too large")
            chunks.append(chunk)
        return b"".join(chunks)

    def json_bytes(body: bytes) -> Response:
        return Response(body, media_type="application/json")

    # ---------------- read endpoints ----------------
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/me")
    def me(request: Request) -> dict[str, object]:
        visitor_uploads = service.visitor_uploads_enabled()
        admin = service.is_admin(request)
        return {
            "name": service.identity(request),
            "is_admin": admin,
            "can_upload": admin or visitor_uploads,
            "visitor_upload": visitor_uploads and not admin,
            "upload_code_required": bool(service.settings.upload_code) and not admin,
            "upload_limits": {
                "max_mb": VISITOR_MAX_BYTES // (1024 * 1024),
                "max_pages": VISITOR_MAX_PAGES,
                "per_day": service.settings.uploads_per_day,
                "remaining_today": service.upload_quota().remaining(service.visitor_key(request))
                if visitor_uploads
                else None,
            },
        }

    @app.get("/api/uploads/pending")
    def uploads_pending(request: Request) -> Response:
        if denied := admin_required(request):
            return denied
        return JSONResponse({"pending": service.pending_uploads().list()})

    @app.get("/api/coverage")
    def coverage() -> Response:
        try:
            return json_bytes(service.coverage())
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.startswith("combustion_atlas.analysis"):
                return error("Analysis not available yet", 503)
            raise

    @app.get("/api/corpus")
    def corpus() -> Response:
        return json_bytes(service.corpus())

    @app.get("/api/landscape")
    def landscape() -> Response:
        return json_bytes(service.landscape())

    @app.get("/api/limits")
    def limits(request: Request) -> dict[str, object]:
        status = service.limiter.status() if service.limiter else {"enabled": False}
        return {**status, "exempt": service.is_paid_exempt(request)}

    @app.get("/api/rag-status")
    def rag_status() -> dict[str, object]:
        config = ProviderConfig.from_environment()
        chunks = vectors = 0
        dimensions = config.embedding_dimensions or {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
        }.get(config.embedding_model)
        if service.atlas.database.is_file():
            with sqlite3.connect(service.atlas.read_database) as connection:
                chunks = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
                vectors = connection.execute(
                    "SELECT count(*) FROM vectors WHERE model_key = ?",
                    (f"openai:{config.embedding_model}:{dimensions}",),
                ).fetchone()[0]
        return {
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

    @app.get("/api/documents/{source_id:path}")
    def document(source_id: str) -> Response:
        atlas = service.atlas
        source = next((s for s in atlas.source_rows() if s["source_id"] == source_id), None)
        path = atlas.document_path(source) if source else None
        if path is None:
            return error("Captured file unavailable", 404)
        return Response(
            path.read_bytes(),
            media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        )

    @app.get("/api/visuals/{artifact_path:path}")
    def visual(artifact_path: str) -> Response:
        from combustion_atlas.rag.visual_models import VisualArtifact

        atlas = service.atlas
        cells = artifact_path.endswith("/cells")
        artifact_id = artifact_path.removesuffix("/cells") if cells else artifact_path
        row = None
        if atlas.database.is_file():
            with DocumentStore(atlas.read_database) as store:
                row = store.connection.execute(
                    "SELECT payload FROM visual_artifacts WHERE artifact_id=?", (artifact_id,)
                ).fetchone()
        artifact = VisualArtifact.model_validate_json(row[0]) if row else None
        if cells:
            from combustion_atlas.rag.tables import resolve_cells

            if artifact is None or artifact.table is None:
                return error("Structured table unavailable", 404)
            return JSONResponse(
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
        if artifact is None:
            return error("Visual unavailable", 404)
        from combustion_atlas.rag.visuals import crop_file

        return Response(crop_file(atlas.root, artifact).read_bytes(), media_type="image/png")

    # ---------------- ask ----------------
    @app.post("/api/ask")
    async def ask(request: Request) -> Response:
        raw = await bounded_json(request)
        evidence = EvidenceRequest.model_validate_json(raw)
        payload = await run_in_threadpool(
            ask_evidence,
            service.atlas,
            evidence,
            limiter=service.limiter,
            exempt=service.is_paid_exempt(request),
        )
        return JSONResponse(payload)

    @app.post("/api/ask/stream")
    async def ask_stream(request: Request) -> Response:
        from .streaming import ask_events

        raw = await bounded_json(request)
        events: Iterator[str] = ask_events(
            service.atlas, raw, limiter=service.limiter, exempt=service.is_paid_exempt(request)
        )
        return StreamingResponse(
            events,
            media_type="application/x-ndjson; charset=utf-8",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    # ---------------- uploads ----------------
    @app.post("/api/upload")
    async def upload(request: Request) -> Response:
        if service.is_admin(request):
            return await admin_upload(request)
        if service.visitor_uploads_enabled():
            return await visitor_upload(request)
        return error("Administrator access required", 403)

    def declared_pdf(request: Request, limit: int, message: str) -> int:
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= limit:
            raise ValueError(message)
        content_type = (request.headers.get("content-type") or "").split(";")[0].strip()
        if content_type != "application/pdf":
            raise ValueError("Upload a PDF file")
        return length

    async def admin_upload(request: Request) -> Response:
        query = request.query_params
        try:
            declared_pdf(request, MAX_UPLOAD_BYTES, "Upload a PDF up to 80 MB")
            body = await read_limited(request, MAX_UPLOAD_BYTES)
            report = await run_in_threadpool(
                ingest_upload,
                service.atlas,
                body,
                filename=query.get("filename", "upload.pdf"),
                investigation=query.get("investigation", "").strip(),
                source_url=query.get("source_url", "").strip() or None,
                embed=query.get("embed") == "1",
            )
            return JSONResponse(report, status_code=201)
        except ValueError as exc:
            return error(str(exc)[:500], 400)
        except OpenAIError:
            return error("Document indexed, but embedding failed. Retry embedding later.", 502)
        except (OSError, sqlite3.Error):
            return error("The upload could not be indexed", 500)

    async def visitor_upload(request: Request) -> Response:
        """Quarantined upload: capped size/pages, optional code, per-visitor and site limits."""
        query = request.query_params
        limiter = service.limiter
        try:
            if service.settings.upload_code and not hmac.compare_digest(
                (request.headers.get("X-Upload-Code") or "").encode(),
                service.settings.upload_code.encode(),
            ):
                return error("Enter the upload code to add a document.", 403)
            declared_pdf(
                request,
                VISITOR_MAX_BYTES,
                f"Upload a PDF up to {VISITOR_MAX_BYTES // (1024 * 1024)} MB",
            )
            visitor = service.visitor_key(request)
            quota = service.upload_quota()
            if quota.remaining(visitor) <= 0:
                raise PaidLimitReached(
                    f"You have used today's {quota.per_day} uploads. Try again after 00:00 UTC.", 0
                )
            body = await read_limited(request, VISITOR_MAX_BYTES)
            pages = count_pages(body)
            if pages > VISITOR_MAX_PAGES:
                raise ValueError(
                    f"Upload a PDF of at most {VISITOR_MAX_PAGES} pages ({pages} found)"
                )
            if limiter is not None:
                decision = limiter.acquire()
                if not decision.allowed:
                    raise PaidLimitReached(
                        (decision.reason or "Site limit reached").replace(
                            "AI answers", "AI calls (answers and uploads)"
                        ),
                        decision.retry_after_s,
                    )
            report = await run_in_threadpool(
                ingest_upload,
                service.atlas,
                body,
                filename=query.get("filename", "upload.pdf"),
                investigation=QUARANTINE,
                source_url=None,
                embed=True,
                folder_name="raw/uploads/visitors",
            )
            if report.get("status") == "added":
                service.pending_uploads().add(report, pages)
            report["quarantined"] = True
            report["uploads_left_today"] = quota.record(visitor)
            return JSONResponse(report, status_code=201)
        except PaidLimitReached as exc:
            return JSONResponse(
                {"error": str(exc), "retry_after_s": exc.retry_after_s}, status_code=429
            )
        except ValueError as exc:
            return error(str(exc)[:500], 400)
        except OpenAIError:
            if limiter is not None:
                limiter.refund()
            return error(
                "Document indexed, but semantic search setup failed. Try again later.", 502
            )
        except (OSError, sqlite3.Error):
            return error("The upload could not be indexed", 500)

    async def moderate(request: Request, approve_upload: bool) -> Response:
        if denied := admin_required(request):
            return denied
        body = json.loads(await bounded_json(request))
        source_id = str(body.get("source_id") or "")
        pending = service.pending_uploads()
        entry = pending.pop(source_id) or {}
        try:
            if approve_upload:
                pages = approve(
                    service.atlas.database, source_id, str(body.get("investigation") or "")
                )
                return JSONResponse({"approved": source_id, "pages": pages})
            delete(service.atlas.database, service.atlas.root, source_id, entry.get("saved_as"))
            return JSONResponse({"deleted": source_id})
        except ValueError:
            if entry:
                pending.add(entry, int(entry.get("pages", 0)))
            raise

    @app.post("/api/uploads/approve")
    async def uploads_approve(request: Request) -> Response:
        return await moderate(request, approve_upload=True)

    @app.post("/api/uploads/delete")
    async def uploads_delete(request: Request) -> Response:
        return await moderate(request, approve_upload=False)

    # ---------------- errors (same messages and codes as before) ----------------
    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        return error(str(exc)[:500], 400)

    @app.exception_handler(ValidationError)
    async def validation_error(_: Request, exc: ValidationError) -> JSONResponse:
        return error(str(exc)[:500], 400)

    @app.exception_handler(PaidLimitReached)
    async def paid_limit(_: Request, exc: PaidLimitReached) -> JSONResponse:
        return JSONResponse(
            {"error": str(exc), "retry_after_s": exc.retry_after_s}, status_code=429
        )

    @app.exception_handler(OpenAIError)
    async def openai_error(_: Request, exc: OpenAIError) -> JSONResponse:
        return error("OpenAI request failed. Check local configuration and try again.", 502)

    @app.exception_handler(sqlite3.Error)
    async def database_error(_: Request, exc: sqlite3.Error) -> JSONResponse:
        LOG.warning("database error: %s", type(exc).__name__)
        return error("Local evidence could not be read", 500)

    @app.exception_handler(OSError)
    async def os_error(_: Request, exc: OSError) -> JSONResponse:
        LOG.warning("file error: %s", type(exc).__name__)
        return error("The request could not be completed", 500)

    # ---------------- the built front end ----------------
    web_dir = settings.web_dir.resolve()

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    def index() -> Response:
        page = web_dir / "index.html"
        if not page.is_file():
            return error("not found", 404)
        return FileResponse(page, media_type="text/html", headers={"Cache-Control": "no-cache"})

    @app.get("/assets/{name:path}", include_in_schema=False)
    def asset(name: str) -> Response:
        # Vite names assets by content hash, so they can be cached for a year.
        return static_file(web_dir / "assets", name, "public, max-age=31536000, immutable")

    @app.get("/{name}", include_in_schema=False)
    def root_file(name: str) -> Response:
        if name == "api":
            return error("not found", 404)
        return static_file(web_dir, name, "public, max-age=3600")

    @app.api_route("/api/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
    def api_not_found(rest: str) -> Response:
        return error("not found", 404)

    def static_file(folder: Path, name: str, cache: str) -> Response:
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file() or path.name == "":
            return error("not found", 404)
        return FileResponse(path, headers={"Cache-Control": cache})

    return app
