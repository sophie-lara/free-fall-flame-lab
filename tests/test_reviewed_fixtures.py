import hashlib
import json
from pathlib import Path

import pytest

from combustion_atlas.review.fixtures import fingerprint, main, prepare


def fixture_workspace(tmp_path: Path) -> Path:
    review = tmp_path / "data/review"
    archive = review / "preserved-review"
    (archive / "additional-candidates").mkdir(parents=True)
    raw = tmp_path / "data/raw/preserved-review"
    raw.mkdir(parents=True)
    (raw / "source.csv").write_text("synthetic source", encoding="utf-8")
    sha = hashlib.sha256((raw / "source.csv").read_bytes()).hexdigest()
    provenance = {
        "file": "source.csv",
        "source_sha256": sha,
        "source_url": "https://example.org/source",
        "row": 2,
        "column": "Fuel Sample Material",
        "page": None,
        "table": None,
        "synthetic": True,
    }
    cell = {
        "original_value": "100 micron film 2 cm wide",
        "original_unit": None,
        "provenance": provenance,
        "value": "100 micron film 2 cm wide",
        "unit": None,
        "qualifier": None,
        "uncertainty": None,
    }
    record = {
        "identity": {"investigation_id": "PSI-25", "test_id": "B3", "sample_id": "SYNTHETIC"},
        "conditions": {"material_description": cell},
        "raw_cells": [{k: cell[k] for k in ("original_value", "original_unit", "provenance")}],
        "outcomes": [],
        "instrument_settings": {},
        "extra_metadata": {},
        "extraction_confidence": None,
        "validation_status": "review_required",
        "human_review_status": "unreviewed",
        "issues": [],
    }
    (archive / "psi-25-b1-b5.json").write_text(json.dumps({"records": [record]}), encoding="utf-8")
    for name in ["flex-table13.json", "saffire-ii.json"]:
        (archive / "additional-candidates" / name).write_text(
            json.dumps({"records": []}), encoding="utf-8"
        )
    note = {
        "investigation_id": "PSI-25",
        "test_id": "B3",
        "candidate_fingerprint": fingerprint(record),
        "reviewer": "Test",
        "decision": "correction_proposed",
        "note": "Synthetic review",
        "evidence": "source.csv row 2",
        "saved_at_utc": "2026-11-14T12:00:00Z",
        "status": "draft",
    }
    (review / "human-notes.jsonl").write_text(json.dumps(note) + "\n", encoding="utf-8")
    entry = {
        "investigation_id": "PSI-25",
        "test_id": "B3",
        "candidate_fingerprint": fingerprint(record),
        "source_sha256": sha,
        "proposed_action": "correction_proposed",
        "supporting_references": ["source.csv row 2"],
        "review_history": [note],
        "latest_confirming_note": {**note, "binding_status": "matched"},
    }
    (review / "reconciled-review.json").write_text(
        json.dumps({"entries": [entry]}), encoding="utf-8"
    )
    return tmp_path


def test_reviewed_corrections_retain_original_and_source(tmp_path: Path) -> None:
    result = prepare(fixture_workspace(tmp_path))[0]
    assert "geometry" not in result.original_candidate["conditions"]
    assert result.reviewed_candidate["conditions"]["geometry"]["value"] == "film"
    assert result.reviewed_candidate["conditions"]["thickness_um"]["value"] == 100
    assert result.reviewed_candidate["conditions"]["width_cm"]["value"] == 2
    assert (
        result.reviewed_candidate["conditions"]["width_cm"]["provenance"]["source_sha256"]
        == result.source_sha256
    )
    assert result.reviewed_candidate["raw_cells"] == result.original_candidate["raw_cells"]
    assert result.confirming_note["reviewer"] == "Test"


def test_changed_source_or_missing_confirmation_is_rejected(tmp_path: Path) -> None:
    root = fixture_workspace(tmp_path)
    (root / "data/raw/preserved-review/source.csv").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        prepare(root)
    (root / "data/raw/preserved-review/source.csv").write_text("synthetic source", encoding="utf-8")
    (root / "data/review/human-notes.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="saved notes"):
        prepare(root)


def test_output_hash_binds_exact_fixture_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = fixture_workspace(tmp_path)
    evidence = root / "evidence.json"
    decisions = root / "decisions.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "fixtures",
            "--workspace",
            str(root),
            "--output",
            str(evidence),
            "--decisions-output",
            str(decisions),
        ],
    )
    main()
    payload = json.loads(decisions.read_text(encoding="utf-8"))
    assert payload["fixture_sha256"] == hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert payload["decisions"][0]["action"] == "correct"
    main()
    evidence.write_text("different", encoding="utf-8")
    with pytest.raises(SystemExit):
        main()
