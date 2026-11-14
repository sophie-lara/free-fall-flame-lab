"""Dependency-light loopback API and static review interface."""

from __future__ import annotations

import json
import mimetypes
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from combustion_atlas.artifacts import CandidateBatch
from combustion_atlas.io import read_json
from combustion_atlas.rag.store import DocumentStore


class AtlasHandler(BaseHTTPRequestHandler):
    workspace = Path.cwd()
    static_dir = Path(__file__).with_name("static")

    def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _candidate_records(self) -> list[dict[str, object]]:
        candidates = sorted((self.workspace / "data/review").glob("*-b1-b5.json"))
        if not candidates:
            return []
        batch = CandidateBatch.model_validate(read_json(candidates[-1]))
        return [record.model_dump(mode="json") for record in batch.records]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json({"status": "ok", "workspace": str(self.workspace)})
            return
        if parsed.path == "/api/experiments":
            self._json({"records": self._candidate_records()})
            return
        if parsed.path == "/api/search":
            query = parse_qs(parsed.query)
            question = query.get("q", [""])[0]
            investigation = query.get("investigation", [None])[0]
            database = self.workspace / "data/embeddings/rag.sqlite3"
            if not database.exists():
                self._json(
                    {
                        "question": question,
                        "results": [],
                        "notice": "Document index has not been built.",
                    }
                )
                return
            with DocumentStore(database) as store:
                results = store.search(question, investigation, 5)
            self._json({"question": question, "results": results})
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/review-notes":
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 100_000:
            self._json({"error": "invalid request size"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            note = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._json({"error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)
            return
        note["saved_at"] = datetime.now(UTC).isoformat()
        path = self.workspace / "data/review/human-notes.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(note, ensure_ascii=False) + "\n")
        self._json({"saved": True}, HTTPStatus.CREATED)

    def _serve_static(self, request_path: str) -> None:
        name = "index.html" if request_path == "/" else request_path.lstrip("/")
        target = (self.static_dir / name).resolve()
        if self.static_dir.resolve() not in target.parents or not target.is_file():
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        payload = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def serve(*, workspace: Path, port: int) -> None:
    AtlasHandler.workspace = workspace.resolve()
    server = ThreadingHTTPServer(("127.0.0.1", port), AtlasHandler)
    print(f"Combustion Atlas: http://127.0.0.1:{port}")
    server.serve_forever()
