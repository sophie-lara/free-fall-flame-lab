"""Experiment candidates and human review notes bound to them by fingerprint.

Used by the review pipeline (for example the holdout lock): candidate batches in
data/review, preserved review records, and draft notes in human-notes.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from combustion_atlas.artifacts import CandidateBatch
from combustion_atlas.io import read_json
from combustion_atlas.normalization.schema import ExperimentRecord

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


class CandidateStore:
    """Candidates and review notes under a project root's data/review directory."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.data = self.root / "data"

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
            raise ValueError("Duplicate candidate identity; choose a distinct project root")
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
