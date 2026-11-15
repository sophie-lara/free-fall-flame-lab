import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from combustion_atlas.ingestion.llm_handoff import csv_batch
from combustion_atlas.review.candidates import CandidateStore, ReviewNote
from combustion_atlas.review.model_candidates import convert


def test_unreviewed_conversion_preserves_source_and_flags(tmp_path: Path) -> None:
    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    source = raw / "test.csv"
    source.write_text(
        "Test #,Sample #,Fuel Sample Material\nB8,1,2 cm 0.2 mm PMMA film\n", encoding="utf-8"
    )
    batch = csv_batch(source, 2)
    result = {
        "status": "unreviewed",
        "record": {
            "investigation_id": "PSI-25",
            "test_id": "B8",
            "record_number": 2,
            "source_file": "data/raw/test.csv",
            "source_sha256": batch.cells[0].source_sha256,
        },
        "source": batch.model_dump(mode="json"),
        "proposal": {
            "schema_version": "mapping-proposal-v1",
            "profile": "bass_ii",
            "fields": [
                {
                    "canonical_field": "width",
                    "source_indexes": [2],
                    "value": 2,
                    "unit": "cm",
                    "qualifier": None,
                    "missingness": "reported",
                    "mapping_status": "proposed",
                    "note": "Axis unspecified",
                }
            ],
        },
        "validation_issues": [],
        "unreferenced_source_cells": [],
        "deterministic_material_fields": {"geometry": "film"},
    }
    path = tmp_path / "01.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    candidate = convert(tmp_path, path)["candidate"]
    assert candidate["human_review_status"] == "unreviewed"
    assert candidate["conditions"]["width"]["original_value"] == "2 cm 0.2 mm PMMA film"
    assert candidate["conditions"]["geometry"]["value"] == "film"
    assert any("unverified_width_interpretation" in i["message"] for i in candidate["issues"])
    assert len(candidate["raw_cells"]) == 3
    candidate_dir = tmp_path / "data/review/model-candidates"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "batch.json").write_text(
        json.dumps({"records": [candidate]}), encoding="utf-8"
    )
    workspace = CandidateStore(tmp_path)
    workspace.save_note(
        ReviewNote(
            investigation_id="PSI-25",
            test_id="B8",
            reviewer="Test",
            decision="needs_research",
            note="Check width",
            evidence="CSV row 2",
        )
    )
    assert workspace.notes()[0]["binding_status"] == "matched"
    source.write_text("Test #,Sample #,Fuel Sample Material\nB8,1,changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash has changed"):
        convert(tmp_path, path)


def test_saffire_conversion_keeps_markers_and_source_notes(tmp_path: Path) -> None:
    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    source = raw / "saffire.csv"
    source.write_text(
        "Sample Number,Material,1-g Spread Rate\n2-7,PMMA,n/a (Nomex)\nNote 1 Derived oxygen,,\n",
        encoding="utf-8",
    )
    batch = csv_batch(source, 2)
    result = {
        "status": "unreviewed",
        "record": {
            "investigation_id": "PSI-99",
            "test_id": "SAFFIRE-II-2-7",
            "record_number": 2,
            "source_file": "data/raw/saffire.csv",
            "source_sha256": batch.cells[0].source_sha256,
        },
        "source": batch.model_dump(mode="json"),
        "proposal": {
            "schema_version": "mapping-proposal-v1",
            "profile": "saffire_ii",
            "fields": [
                {
                    "canonical_field": "spread_rate_1g",
                    "source_indexes": [2],
                    "value": "n/a (Nomex)",
                    "unit": None,
                    "qualifier": "Nomex",
                    "missingness": "source_marker",
                    "mapping_status": "direct",
                    "note": None,
                }
            ],
        },
        "validation_issues": [],
        "unreferenced_source_cells": [],
    }
    path = tmp_path / "01.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    converted = convert(tmp_path, path)
    candidate = converted["candidate"]
    assert candidate["identity"]["test_id"] == "SAFFIRE-II-2-7"
    assert candidate["outcomes"][0]["value"] == "n/a (Nomex)"
    assert candidate["outcomes"][0]["qualifier"] == "Nomex"
    assert converted["field_mappings"][0]["missingness"] == "source_marker"
    assert converted["field_mappings"][0]["source_cells"][0]["original_value"] == "n/a (Nomex)"
    assert candidate["extra_metadata"]["source_note_1"]["original_value"] == "Note 1 Derived oxygen"


def test_index_import_selects_flags_and_audit_only(tmp_path: Path, monkeypatch) -> None:
    from combustion_atlas.review import model_candidates

    result_dir = tmp_path / "results"
    result_dir.mkdir()
    plan = {"records": [{}, {}, {}]}
    (result_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    plan_hash = hashlib.sha256(
        json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    entries = []
    for i in range(3):
        folder = result_dir / f"row-{i:04}"
        folder.mkdir()
        path = folder / "01.json"
        path.write_text(str(i), encoding="utf-8")
        entries.append(
            {
                "result_path": path.relative_to(result_dir).as_posix(),
                "result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "review_flagged": i == 0,
                "audit_sample": i == 1,
            }
        )
    index = {
        "schema_version": "full-run-review-index-v1",
        "plan_sha256": plan_hash,
        "completed": 3,
        "records": entries,
    }
    index_path = result_dir / "review-index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")

    def convert_fake(root, path):
        return {
            "candidate": {"identity": {"investigation_id": "PSI-25", "test_id": path.parent.name}},
            "result_file": path.name,
            "result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "field_mappings": [],
            "source_context": [],
        }

    monkeypatch.setattr(model_candidates, "convert", convert_fake)
    monkeypatch.setattr(
        model_candidates,
        "CandidateStore",
        lambda _: SimpleNamespace(records=lambda: [], preserved=lambda: []),
    )
    output = tmp_path / "data/review/model-candidates/out.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "adapter",
            "--workspace",
            str(tmp_path),
            "--results",
            str(result_dir),
            "--review-index",
            str(index_path),
            "--output",
            str(output),
        ],
    )
    model_candidates.main()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert [r["identity"]["test_id"] for r in saved["records"]] == ["row-0000", "row-0001"]

    everything = tmp_path / "data/review/model-candidates/all.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [*sys.argv[:-1], str(everything), "--all-rows"],
    )
    model_candidates.main()
    saved = json.loads(everything.read_text(encoding="utf-8"))
    assert [r["identity"]["test_id"] for r in saved["records"]] == [
        "row-0000",
        "row-0001",
        "row-0002",
    ]
