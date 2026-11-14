from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from combustion_atlas.ingestion.llm_handoff import SourceBatch, SourceCellRef
from combustion_atlas.ingestion.mapping_contract import MappedField, MappedRow
from combustion_atlas.ingestion.mapping_runner import run


def test_regression_runner_saves_unreviewed_and_usage(tmp_path: Path, monkeypatch) -> None:
    import json

    import combustion_atlas.ingestion.mapping_runner as runner

    source = SourceBatch(cells=[SourceCellRef(source_sha256="a" * 64, filename="s.csv", kind="csv",
        csv_record=2, csv_column="Test #", text="B1", state="present")])
    record = {"test_id": "B1", "investigation_id": "PSI-25", "source_sha256": "a" * 64}
    monkeypatch.setattr(runner, "prepare", lambda *_: [(record, source, "bass_ii", Decimal("0.1"))])
    output = tmp_path / "out"
    assert run(tmp_path, tmp_path / "plan", output)["dry_run"]
    assert not output.exists()
    field = MappedField(canonical_field="test_id", source_indexes=[0], value="B1", unit=None,
                        qualifier=None, missingness="reported", mapping_status="direct", note=None)
    row = MappedRow(schema_version="mapping-proposal-v1", profile="bass_ii", fields=[field])
    usage = SimpleNamespace(model_dump=lambda **_: {"input_tokens": 1, "output_tokens": 1})
    response = SimpleNamespace(output_parsed=row, usage=usage, model="fake", id="fake")
    client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **_: response))
    run(tmp_path, tmp_path / "plan", output, allow_calls=True, client=client)
    data = json.loads((output / "01.json").read_text(encoding="utf-8"))
    assert data["status"] == "unreviewed"
    assert data["proposal"]["fields"][0]["canonical_field"] == "test_id"
    assert '"status": "complete"' in (output / "ledger.jsonl").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        run(tmp_path, tmp_path / "plan", output, allow_calls=True, client=client)


def test_provider_failure_leaves_reserved_ledger_and_no_retry(tmp_path: Path, monkeypatch) -> None:
    import combustion_atlas.ingestion.mapping_runner as runner

    source = SourceBatch(cells=[SourceCellRef(source_sha256="a" * 64, filename="s.csv", kind="csv",
        csv_record=2, csv_column="Test #", text="B1", state="present")])
    record = {"test_id": "B1", "investigation_id": "PSI-25", "source_sha256": "a" * 64}
    monkeypatch.setattr(runner, "prepare", lambda *_: [(record, source, "bass_ii", Decimal("0.1"))])
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("uncertain provider error")

    output = tmp_path / "out"
    client = SimpleNamespace(responses=SimpleNamespace(parse=fail))
    with pytest.raises(RuntimeError, match="uncertain"):
        run(tmp_path, tmp_path / "plan", output, allow_calls=True, client=client)
    assert len(calls) == 1
    assert '"status": "reserved"' in (output / "ledger.jsonl").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        run(tmp_path, tmp_path / "plan", output, allow_calls=True, client=client)
    assert len(calls) == 1
