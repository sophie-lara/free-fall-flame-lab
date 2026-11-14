from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from combustion_atlas.ingestion.llm_handoff import (
    FieldProposal,
    Proposal,
    SourceBatch,
    SourceCellRef,
    check_proposal,
)
from combustion_atlas.ingestion.pilot_runner import (
    deterministic_bass_fields,
    identity_issue,
    reserve,
    run,
)


def test_missingness_preserves_source_and_flags_mismatch() -> None:
    batch = SourceBatch(cells=[SourceCellRef(source_sha256="a" * 64, filename="a.csv",
        kind="csv", csv_record=2, csv_column="x", text="N/A", state="present")])
    field = FieldProposal(field="x", value=None, unit=None, qualifier=None,
                          cell_indexes=[0], review_reason=None, missingness="source_marker")
    assert check_proposal(batch, Proposal(investigation_id="i", test_id="t", fields=[field])) == []
    field.missingness = "source_blank"
    issues = check_proposal(batch, Proposal(investigation_id="i", test_id="t", fields=[field]))
    assert issues[0].code == "missingness_mismatch"
    assert issues[0].source_cells[0].text == "N/A"


def test_inferred_values_always_require_review() -> None:
    batch = SourceBatch(cells=[SourceCellRef(source_sha256="a" * 64, filename="a.csv",
        kind="csv", csv_record=2, csv_column="x", text="037", state="present")])
    field = FieldProposal(field="x", value=0.37, unit="mm", qualifier=None,
                          cell_indexes=[0], review_reason=None, missingness="inferred")
    issues = check_proposal(batch, Proposal(investigation_id="i", test_id="t", fields=[field]))
    assert issues[0].code == "inferred"


def test_bass_dimensions_do_not_require_material_identity() -> None:
    def cell(column: str, value: str) -> SourceCellRef:
        return SourceCellRef(source_sha256="a" * 64, filename="a.csv", kind="csv",
                             csv_record=2, csv_column=column, text=value, state="present")

    batch = SourceBatch(cells=[cell("Test #", "B3"),
        cell("Fuel Sample Material", "100 micron film 2 cm wide")])
    found = deterministic_bass_fields(batch, "PSI-25")
    assert found["material"] is None
    assert found["geometry"] == "film"
    assert found["dimensions"]["thickness_um"]["value"] == 100
    assert found["dimensions"]["width_cm"]["value"] == 2
    assert found["dimensions"]["width_cm"]["original_value"] == "100 micron film 2 cm wide"


def test_identity_aliases_and_conflicts() -> None:
    saffire = {"investigation_id": "PSI-99", "test_id": "SAFFIRE-II-2-4"}
    proposal = Proposal(investigation_id="SAFFIRE-2", test_id="2-4", fields=[])
    assert identity_issue(saffire, proposal) is None
    proposal.test_id = "2-2"
    assert identity_issue(saffire, proposal) == "identity_mismatch"
    proposal.test_id = "unrecognized"
    assert identity_issue(saffire, proposal) == "identity_unresolved"
    flex = {"investigation_id": "PSI-69", "test_id": "FLEX-T13-N2"}
    proposal = Proposal(investigation_id="PSI-69",
                        test_id="FLEX background study, Table 13, N2 row", fields=[])
    assert identity_issue(flex, proposal) is None


def test_dry_run_and_existing_output_do_not_call_provider(tmp_path: Path, monkeypatch) -> None:
    import combustion_atlas.ingestion.pilot_runner as runner

    batch = SourceBatch(cells=[SourceCellRef(source_sha256="a" * 64, filename="a.csv",
        kind="csv", csv_record=2, csv_column="x", text="1", state="present")])
    monkeypatch.setattr(runner, "build", lambda *_: [({}, batch, "payload", Decimal("0.1"))])
    class FakeClient:
        @property
        def responses(self):
            raise AssertionError("Provider must not be called")
    output = tmp_path / "out"
    assert run(tmp_path, tmp_path / "plan", output, client=FakeClient())["dry_run"]
    assert not output.exists()
    output.mkdir()
    with pytest.raises(FileExistsError):
        run(tmp_path, tmp_path / "plan", output, allow_calls=True, client=FakeClient())
    assert reserve("example") < Decimal("2")


def test_failure_records_reservation_and_does_not_retry(tmp_path: Path, monkeypatch) -> None:
    import combustion_atlas.ingestion.pilot_runner as runner

    batch = SourceBatch(cells=[SourceCellRef(source_sha256="a" * 64, filename="a.csv",
        kind="csv", csv_record=2, csv_column="x", text="1", state="present")])
    monkeypatch.setattr(runner, "build", lambda *_: [({}, batch, "payload", Decimal("0.1"))])
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("uncertain provider failure")

    output = tmp_path / "out"
    client = SimpleNamespace(responses=SimpleNamespace(parse=fail))
    with pytest.raises(RuntimeError, match="uncertain"):
        run(tmp_path, tmp_path / "plan", output, allow_calls=True, client=client)
    assert len(calls) == 1
    assert '"status": "reserved"' in (output / "ledger.jsonl").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        run(tmp_path, tmp_path / "plan", output, allow_calls=True, client=client)
    assert len(calls) == 1


def test_success_writes_usage_and_unreviewed_proposal(tmp_path: Path, monkeypatch) -> None:
    import json

    import combustion_atlas.ingestion.pilot_runner as runner

    batch = SourceBatch(cells=[SourceCellRef(source_sha256="a" * 64, filename="a.csv",
        kind="csv", csv_record=2, csv_column="x", text="1", state="present")])
    record = {"investigation_id": "i", "test_id": "t", "split": "holdout"}
    monkeypatch.setattr(runner, "build", lambda *_: [(record, batch, "payload", Decimal("0.1"))])
    proposal = Proposal(investigation_id="i", test_id="t", fields=[
        FieldProposal(field="x", value=1, unit=None, qualifier=None, cell_indexes=[0],
                      review_reason=None, missingness="reported")])
    usage = SimpleNamespace(input_tokens=10, output_tokens=10,
                            model_dump=lambda **_: {"input_tokens": 10, "output_tokens": 10})
    response = SimpleNamespace(output_parsed=proposal, usage=usage, id="fake", model="gpt-6-luna")
    client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **_: response))
    output = tmp_path / "out"
    run(tmp_path, tmp_path / "plan", output, allow_calls=True, client=client)
    result = json.loads((output / "01.json").read_text(encoding="utf-8"))
    assert result["status"] == "unreviewed"
    assert result["source"]["cells"][0]["text"] == "1"
    assert '"status": "complete"' in (output / "ledger.jsonl").read_text(encoding="utf-8")
