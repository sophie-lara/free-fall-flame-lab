import json
from pathlib import Path

import pytest

from combustion_atlas.ingestion import holdout_runner
from combustion_atlas.ingestion.mapping_contract import mapping_request
from combustion_atlas.ingestion.table_parser import sha256_file


def test_holdout_requests_exclude_review_notes_and_check_snapshots(
    tmp_path: Path, monkeypatch
) -> None:
    raw = tmp_path / "data/raw"
    processed = tmp_path / "data/processed"
    raw.mkdir(parents=True)
    processed.mkdir(parents=True)
    bass = raw / "bass.csv"
    saffire = raw / "saffire.csv"
    bass.write_text("Test #,value\nB6,1\nB7,2\n", encoding="utf-8")
    saffire.write_text("Sample Number,value\n2-6,3\n2-7,4\n", encoding="utf-8")
    selection = []
    for investigation, path, ids in [
        ("PSI-25", bass, ("B6", "B7")),
        ("PSI-99", saffire, ("2-6", "2-7")),
    ]:
        for number, test_id in enumerate(ids, 2):
            selection.append(
                {
                    "investigation_id": investigation,
                    "source_identity": test_id,
                    "source_file": path.relative_to(tmp_path).as_posix(),
                    "record_number": number,
                    "source_sha256": sha256_file(path),
                }
            )
    (processed / "holdout-selection-v1.json").write_text(json.dumps({"rows": selection}))
    snapshot = {"private_review": "DO NOT SEND THIS REVIEW"}
    (processed / "holdout-reviews-v1.json").write_text(json.dumps(snapshot))
    monkeypatch.setattr(holdout_runner, "verify_reviews", lambda _: snapshot)
    requests = holdout_runner.prepare(tmp_path)
    assert len(requests) == 4
    for _, batch, profile, _ in requests:
        assert "DO NOT SEND THIS REVIEW" not in json.dumps(mapping_request(profile, batch))
    monkeypatch.setattr(holdout_runner, "verify_reviews", lambda _: {"changed": True})
    with pytest.raises(ValueError, match="changed"):
        holdout_runner.prepare(tmp_path)
