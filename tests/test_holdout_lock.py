import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from combustion_atlas.review import holdout_lock


def test_lock_requires_matching_source_and_review_binding(tmp_path: Path, monkeypatch) -> None:
    processed = tmp_path / "data/processed"
    processed.mkdir(parents=True)
    rows = [
        {
            "investigation_id": "PSI-25",
            "source_identity": f"B{i}",
            "source_file": "data/raw/source.csv",
            "source_sha256": "a" * 64,
            "record_number": i + 1,
        }
        for i in range(1, 5)
    ]
    (processed / "holdout-selection-v1.json").write_text(json.dumps({"rows": rows}))
    candidates = [
        {"investigation_id": "PSI-25", "test_id": f"B{i}", "raw_cells": {"Test #": f"B{i}"}}
        for i in range(1, 5)
    ]
    records = [
        SimpleNamespace(
            investigation_id=c["investigation_id"],
            test_id=c["test_id"],
            model_dump=lambda c=c, **_: c,
        )
        for c in candidates
    ]
    notes = []
    for candidate in candidates:
        digest = hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        notes.append(
            {
                "investigation_id": candidate["investigation_id"],
                "test_id": candidate["test_id"],
                "binding_status": "matched",
                "candidate_fingerprint": digest,
                "decision": "accept_extraction",
                "saved_at_utc": "2026-01-01T00:00:00+00:00",
            }
        )
    workspace = SimpleNamespace(records=lambda: records, preserved=lambda: [], notes=lambda: notes)
    monkeypatch.setattr(holdout_lock, "CandidateStore", lambda _: workspace)
    table = SimpleNamespace(
        sha256="a" * 64,
        rows=[SimpleNamespace(record_number=i + 1, cells={"Test #": f"B{i}"}) for i in range(1, 5)],
    )
    monkeypatch.setattr(holdout_lock, "read_csv_losslessly", lambda _: table)
    assert len(holdout_lock.prepare(tmp_path)["records"]) == 4
    notes[0]["candidate_fingerprint"] = "wrong"
    with pytest.raises(ValueError, match="not bound"):
        holdout_lock.prepare(tmp_path)
    notes[0]["candidate_fingerprint"] = hashlib.sha256(
        json.dumps(candidates[0], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    table.rows[0].cells["Test #"] = "changed"
    with pytest.raises(ValueError, match="source cells differ"):
        holdout_lock.prepare(tmp_path)
