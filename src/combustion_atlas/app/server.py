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
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from combustion_atlas.artifacts import CandidateBatch
from combustion_atlas.io import read_json
from combustion_atlas.normalization.schema import ExperimentRecord
from combustion_atlas.rag.store import DocumentStore
from combustion_atlas.retrieval.structured import filter_records

_WRITE_LOCK = threading.Lock()


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
        ]
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
        for note in notes:
            note.setdefault("saved_at_utc", note.get("saved_at"))
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
        entry = {
            **note.model_dump(),
            "saved_at_utc": datetime.now(UTC).isoformat(),
            "status": "draft",
        }
        path = self.data / "review/human-notes.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK, path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

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
    static_dir = Path(__file__).with_name("static")

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
        return host in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def do_GET(self) -> None:  # noqa: N802
        if not self._allowed_host():
            self._json({"error": "Local requests required"}, HTTPStatus.FORBIDDEN)
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
        elif parsed.path == "/api/overview":
            self._json(atlas.overview())
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
                results = store.search(question, query.get("investigation"), k)
            self._json({"question": question, "results": results})
        elif parsed.path.startswith("/api/documents/"):
            sid = parsed.path.removeprefix("/api/documents/")
            source = next((s for s in atlas.source_rows() if s["source_id"] == sid), None)
            path = atlas.document_path(source) if source else None
            if path is None:
                self._json({"error": "Captured file unavailable"}, HTTPStatus.NOT_FOUND)
            else:
                self._content(
                    path.read_bytes(),
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                )
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
        if not self._allowed_host() or self.headers.get("Origin") not in {
            None,
            f"http://{self.headers.get('Host')}",
        }:
            self._json({"error": "Same-origin local requests required"}, HTTPStatus.FORBIDDEN)
            return
        if urlparse(self.path).path not in {"/api/reviews", "/api/review-notes"}:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 32768 or self.headers.get_content_type() != "application/json":
                raise ValueError("A bounded JSON review note is required")
            note = ReviewNote.model_validate_json(self.rfile.read(length))
            self._json(self.atlas.save_note(note), HTTPStatus.CREATED)
        except (ValueError, ValidationError) as exc:
            self._json({"error": str(exc)[:500]}, HTTPStatus.BAD_REQUEST)
        except OSError:
            self._json(
                {"error": "Review note could not be saved"}, HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def _serve_static(self, request_path: str) -> None:
        names = {
            "/": "index.html",
            "/index.html": "index.html",
            "/app.js": "app.js",
            "/styles.css": "styles.css",
        }
        if request_path not in names:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        target = self.static_dir / names[request_path]
        self._content(
            target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        )


def serve(*, workspace: Path, port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    handler = type("WorkspaceHandler", (AtlasHandler,), {"workspace": workspace.resolve()})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"Combustion Atlas: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
