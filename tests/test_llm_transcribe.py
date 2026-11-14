import json
import sys
from pathlib import Path
from types import SimpleNamespace

from combustion_atlas.ingestion import llm_transcribe
from combustion_atlas.ingestion.llm_handoff import FieldProposal, Proposal


def test_cli_dry_run_does_not_create_client_or_output(tmp_path: Path, monkeypatch, capsys) -> None:
    source = tmp_path / "source.csv"
    source.write_text("test,value\nA,12\n", encoding="utf-8")
    output = tmp_path / "proposal.json"

    def fail_client():
        raise AssertionError("Dry run must not create an API client")

    monkeypatch.setattr(llm_transcribe, "OpenAI", fail_client)
    monkeypatch.setattr(sys, "argv", ["transcribe", str(source), "--record", "2", "--model",
                                     "example", "--output", str(output)])
    llm_transcribe.main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["dry_run"] is True
    assert summary["planned_calls"] == 1
    assert not output.exists()


def test_explicit_run_saves_unreviewed_output_using_fake_client(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "source.csv"
    source.write_text("test,value\nA,037\n", encoding="utf-8")
    output = tmp_path / "proposal.json"
    proposal = Proposal(investigation_id="test", test_id="A", fields=[
        FieldProposal(field="value", value=0.37, unit="mm", qualifier=None,
                      cell_indexes=[1], review_reason="Possible missing decimal")])
    response = SimpleNamespace(output_parsed=proposal, usage=None, model="fake", id="fake-id")
    client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: response))
    monkeypatch.setattr(llm_transcribe, "OpenAI", lambda **kwargs: client)
    monkeypatch.setattr(sys, "argv", ["transcribe", str(source), "--record", "2", "--model",
        "fake", "--output", str(output), "--allow-provider-calls"])
    llm_transcribe.main()
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "unreviewed"
    assert result["source"]["cells"][1]["text"] == "037"
    assert result["issues"][0]["code"] == "model_uncertainty"
    assert '"037"' in output.with_suffix(".review.md").read_text(encoding="utf-8")
    assert json.loads(capsys.readouterr().out)["dry_run"] is False
