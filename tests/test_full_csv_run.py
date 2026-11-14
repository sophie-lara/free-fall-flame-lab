import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from combustion_atlas.ingestion import full_csv_run
from combustion_atlas.ingestion.table_parser import sha256_file


def test_plan_covers_series_and_preserves_saffire_notes(tmp_path: Path, monkeypatch) -> None:
    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    bass = raw / "bass.csv"
    saffire = raw / "saffire.csv"
    bass.write_text("Test #,Fuel Sample Material\nB1,film\nM1,film\nO3a,rod\n", encoding="utf-8")
    saffire.write_text(
        "Sample Number,Material\n2-1,PMMA\nF1C1,video\nNote 1 Derived from measurements,\n",
        encoding="utf-8",
    )
    reviewed = SimpleNamespace(
        investigation_id="PSI-25",
        test_id="B1",
        provenance=[SimpleNamespace(source_sha256=sha256_file(bass))],
    )
    monkeypatch.setattr(
        full_csv_run,
        "Workspace",
        lambda _: SimpleNamespace(records=lambda: [reviewed], preserved=lambda: []),
    )
    monkeypatch.setattr(full_csv_run, "environment", lambda _: {"code": "fixture"})
    plan = full_csv_run.create_plan(tmp_path, {"PSI-25": bass, "PSI-99": saffire}, Decimal("2"))
    assert [item["record"]["test_id"] for item in plan["records"]] == [
        "M1",
        "O3a",
        "SAFFIRE-II-2-1",
    ]
    assert {item["reason"] for item in plan["excluded"]} == {
        "existing_review_candidate",
        "source_note",
        "non_run",
    }
    requests = full_csv_run.rebuild(tmp_path, plan)
    context = requests[-1][1].context
    assert "Note 1 Derived from measurements" in context[0]
    assert '"source_record_number": 4' in context[0]
    saffire.write_text(saffire.read_text() + "changed,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source has changed"):
        full_csv_run.rebuild(tmp_path, plan)


def test_execution_resumes_completed_and_stops_uncertain(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    target = root / "data/processed/full-runs/test"
    source = SimpleNamespace()
    requests = [
        ({"test_id": "B1"}, source, "bass_ii", Decimal("0.01")),
        ({"test_id": "B2"}, source, "bass_ii", Decimal("0.01")),
    ]
    monkeypatch.setattr(full_csv_run, "rebuild", lambda *_: requests)
    calls = []

    def fake_run(root, plan, output, **kwargs):
        calls.append(output.name)
        output.mkdir()
        (output / "01.json").write_text(
            json.dumps(
                {
                    "record": {"investigation_id": "PSI-25", "test_id": "B1"},
                    "validation_issues": [],
                    "source_issues": [],
                    "unreferenced_source_cells": [],
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(full_csv_run, "run", fake_run)
    plan = {"budget_usd": "2.00", "reservation_usd": "0.02", "records": [{}, {}]}
    assert full_csv_run.execute(root, plan, target, allow_calls=False)["dry_run"]
    assert not target.exists()
    full_csv_run.execute(root, plan, target, allow_calls=True)
    assert "Suggested audit" in (target / "review-report.md").read_text(encoding="utf-8")
    full_csv_run.execute(root, plan, target, allow_calls=True, resume=True)
    assert calls == ["row-0001", "row-0002"]
    (target / "row-0001/01.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="missing or changed"):
        full_csv_run.execute(root, plan, target, allow_calls=True, resume=True)
    ledger = target / "run-ledger.jsonl"
    lines = ledger.read_text(encoding="utf-8").splitlines()
    ledger.write_text("\n".join(lines[:1]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="uncertain status"):
        full_csv_run.execute(root, plan, target, allow_calls=True, resume=True)


def test_full_orchestrator_uses_mapping_runner_with_fake_provider(
    tmp_path: Path, monkeypatch
) -> None:
    from combustion_atlas.ingestion.csv_batch_runner import prepare
    from combustion_atlas.ingestion.mapping_contract import MappedField, MappedRow

    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    source = raw / "source.csv"
    source.write_text("Test #,Fuel Sample Material\nB8,PMMA film\n", encoding="utf-8")
    requests = prepare(tmp_path, source, "PSI-25", [2])
    monkeypatch.setattr(full_csv_run, "rebuild", lambda *_: requests)
    field = MappedField(
        canonical_field="test_id",
        source_indexes=[0],
        value="B8",
        unit=None,
        qualifier=None,
        missingness="reported",
        mapping_status="direct",
        note=None,
    )
    row = MappedRow(schema_version="mapping-proposal-v1", profile="bass_ii", fields=[field])
    usage = SimpleNamespace(model_dump=lambda **_: {"input_tokens": 10, "output_tokens": 10})
    response = SimpleNamespace(output_parsed=row, usage=usage, model="fake", id="fake-id")
    client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **_: response))
    plan = {"budget_usd": "2", "reservation_usd": str(requests[0][3]), "records": [{}]}
    output = tmp_path / "data/processed/full-runs/synthetic"
    summary = full_csv_run.execute(tmp_path, plan, output, allow_calls=True, client=client)
    assert summary["completed"] == 1
    result = json.loads((output / "row-0001/01.json").read_text(encoding="utf-8"))
    assert result["status"] == "unreviewed"
    assert result["source"]["cells"][0]["text"] == "B8"
    assert (output / "review-index.json").is_file()
