"""Visitor uploads on a public deployment: caps, quarantine registry, approve/delete.

A visitor's PDF is indexed under the QUARANTINE investigation, so it is searchable
only by the browser that uploaded it (requests name it in include_sources) and stays
out of shared search results, counts and maps until an administrator approves it.
"""

from __future__ import annotations

import io
import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from combustion_atlas.rag.store import QUARANTINE, DocumentStore

VISITOR_MAX_BYTES = 15 * 1024 * 1024
VISITOR_MAX_PAGES = 60
SOURCE_ID = re.compile(r"^[a-f0-9]{16}$")
INVESTIGATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.()-]{0,78}")


def count_pages(body: bytes) -> int:
    from pypdf import PdfReader

    try:
        return len(PdfReader(io.BytesIO(body)).pages)
    except Exception as exc:  # malformed or encrypted PDFs are refused, not indexed
        raise ValueError("The PDF could not be read") from exc


class PendingUploads:
    """Small JSON registry of quarantined uploads, safe across request threads."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> list[dict[str, Any]]:
        try:
            items: list[dict[str, Any]] = json.loads(self.path.read_text(encoding="utf-8"))
            return items
        except (OSError, ValueError):
            return []

    def _write(self, items: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(items, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read()

    def add(self, report: dict[str, Any], pages: int) -> None:
        with self._lock:
            items = [i for i in self._read() if i["source_id"] != report["source_id"]]
            items.append(
                {
                    "source_id": report["source_id"],
                    "filename": report.get("filename"),
                    "saved_as": report.get("saved_as"),
                    "pages": pages,
                    "passages": report.get("chunks_added", 0),
                    "uploaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            )
            self._write(items)

    def pop(self, source_id: str) -> dict[str, Any] | None:
        with self._lock:
            items = self._read()
            match = next((i for i in items if i["source_id"] == source_id), None)
            if match is not None:
                self._write([i for i in items if i["source_id"] != source_id])
            return match


def approve(database: Path, source_id: str, investigation: str) -> int:
    """Move a quarantined source into the shared corpus under a real investigation."""
    if not SOURCE_ID.fullmatch(source_id):
        raise ValueError("Unknown upload")
    if not INVESTIGATION.fullmatch(investigation) or investigation == QUARANTINE:
        raise ValueError("Choose an investigation ID for the approved document")
    with DocumentStore(database) as store, store.connection:
        changed = store.connection.execute(
            "UPDATE pages SET investigation_id=? WHERE source_id=? AND investigation_id=?",
            (investigation, source_id, QUARANTINE),
        ).rowcount
        store.connection.execute(
            "UPDATE chunks SET investigation_id=? WHERE source_id=? AND investigation_id=?",
            (investigation, source_id, QUARANTINE),
        )
    if not changed:
        raise ValueError("That upload is not awaiting review")
    return int(changed)


def delete(database: Path, root: Path, source_id: str, saved_as: str | None) -> None:
    """Remove a quarantined source, its vectors and the saved PDF."""
    if not SOURCE_ID.fullmatch(source_id):
        raise ValueError("Unknown upload")
    with DocumentStore(database) as store:
        quarantined = store.connection.execute(
            "SELECT 1 FROM pages WHERE source_id=? AND investigation_id=? LIMIT 1",
            (source_id, QUARANTINE),
        ).fetchone()
        if quarantined is None:
            raise ValueError("Only uploads awaiting review can be deleted here")
        store.remove_document(source_id)
    if saved_as:
        path = (root / saved_as).resolve()
        if path.is_relative_to((root / "data/raw/uploads").resolve()) and path.is_file():
            path.unlink()


class UploadQuota:
    """Per-visitor uploads per UTC day. Keys are hashed (no raw IPs are stored)."""

    def __init__(self, path: Path, per_day: int = 3):
        self.path = path
        self.per_day = per_day
        self._lock = threading.Lock()

    @staticmethod
    def key(identity: str) -> str:
        import hashlib

        return hashlib.sha256(f"combustion-atlas-upload:{identity}".encode()).hexdigest()[:24]

    def _state(self, today: str) -> dict[str, Any]:
        try:
            state: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        if state.get("date") != today:
            state = {"date": today, "counts": {}}
        return state

    def remaining(self, identity: str, now: datetime | None = None) -> int:
        today = (now or datetime.now(UTC)).date().isoformat()
        with self._lock:
            used = int(self._state(today)["counts"].get(self.key(identity), 0))
        return max(0, self.per_day - used)

    def record(self, identity: str, now: datetime | None = None) -> int:
        """Count one successful upload; returns uploads left today."""
        today = (now or datetime.now(UTC)).date().isoformat()
        with self._lock:
            state = self._state(today)
            key = self.key(identity)
            state["counts"][key] = int(state["counts"].get(key, 0)) + 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state), encoding="utf-8")
            temporary.replace(self.path)
            return max(0, self.per_day - int(state["counts"][key]))


_SHARED: dict[tuple[str, Path], Any] = {}
_SHARED_LOCK = threading.Lock()


def pending_for(path: Path) -> PendingUploads:
    """One registry per file, shared by all request threads (so its lock is shared)."""
    with _SHARED_LOCK:
        return _SHARED.setdefault(("pending", path), PendingUploads(path))  # type: ignore[no-any-return]


def quota_for(path: Path, per_day: int) -> UploadQuota:
    with _SHARED_LOCK:
        quota = _SHARED.setdefault(("quota", path), UploadQuota(path, per_day))
        quota.per_day = per_day
        return quota  # type: ignore[no-any-return]
