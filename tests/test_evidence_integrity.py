import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from combustion_atlas.artifacts import CandidateBatch, SourceIdentity
from combustion_atlas.ingestion.models import RawRow
from combustion_atlas.ingestion.table_parser import read_csv_losslessly
from combustion_atlas.normalization.extractor import extract_bass_row
from combustion_atlas.review.workflow import apply_decisions, fingerprint_record


@pytest.mark.parametrize("content", ["A,A\n1,2\n", "A, a \n1,2\n", "A,B\n1,2,3\n", "A,B\n1\n"])
def test_reject_lossy_csv(tmp_path: Path, content: str) -> None:
    p = tmp_path / "bad.csv"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        read_csv_losslessly(p)


@pytest.mark.parametrize(
    "raw,value,qualifier",
    [
        ("21-23", None, "unparsed_or_qualified"),
        ("~21.5", None, "unparsed_or_qualified"),
        ("<0.1", None, "unparsed_or_qualified"),
        ("1e-3", 0.001, None),
        ("n/a", None, "source_marker"),
        ("", None, "source_blank"),
    ],
)
def test_numbers_preserve_semantics(raw: str, value: float | None, qualifier: str | None) -> None:
    row = RawRow(record_number=2, cells={"Test #": "T1", "Calibrated initial O2 % by vol": raw})
    r = extract_bass_row(
        row,
        investigation_id="SYNTHETIC",
        source_url="https://example.org/source",
        source_sha256="a" * 64,
    )
    assert r.conditions.oxygen_pct is not None
    assert r.conditions.oxygen_pct.value == value and r.conditions.oxygen_pct.qualifier == qualifier
    assert r.conditions.oxygen_pct.original_value == raw
    if qualifier == "unparsed_or_qualified":
        assert r.validation_status == "review_required"


@pytest.mark.parametrize(
    "description,geometry,thickness,width",
    [("100 micron film 2 cm wide", "film", 100, 2), ("200 micron 2 cm wide", None, 200, 2)],
)
def test_reviewed_dimensions_independent(
    description: str, geometry: str | None, thickness: float, width: float
) -> None:
    row = RawRow(record_number=2, cells={"Test #": "T1", "Fuel Sample Material": description})
    r = extract_bass_row(
        row,
        investigation_id="SYNTHETIC",
        source_url="https://example.org/source",
        source_sha256="a" * 64,
    )
    assert r.conditions.geometry == geometry and r.conditions.material is None
    assert r.conditions.dimensions["thickness_um"].value == thickness
    assert r.conditions.dimensions["width_cm"].value == width
    assert r.conditions.dimensions["width_cm"].original_value == description


def test_adjudication_preserves_flags_and_requires_complete_unique_decisions(
    tmp_path: Path,
) -> None:
    row = RawRow(record_number=2, cells={"Test #": "T1", "Calibrated initial O2 % by vol": "120"})
    r = extract_bass_row(
        row,
        investigation_id="SYNTHETIC",
        source_url="https://example.org/source",
        source_sha256="a" * 64,
    )
    batch = CandidateBatch(
        generated_at=datetime.now(UTC),
        source=SourceIdentity(
            investigation_id="SYNTHETIC",
            source_url="https://example.org/source",
            local_path="synthetic.csv",
            sha256="a" * 64,
        ),
        records=[r],
    )
    candidate = tmp_path / "candidate.json"
    candidate.write_text(batch.model_dump_json(), encoding="utf-8")
    d = {
        "investigation_id": "SYNTHETIC",
        "test_id": "T1",
        "candidate_fingerprint": fingerprint_record(r),
        "action": "accept",
        "reviewer": "Test",
        "reviewed_at": "2026-11-14T12:00:00Z",
        "rationale": "Test fixture",
        "supporting_references": ["Source record 2"],
    }
    decisions = tmp_path / "decisions.json"
    out = tmp_path / "audit.json"

    def write(items: list[dict]) -> None:
        decisions.write_text(
            json.dumps({"candidate_file": str(candidate), "decisions": items}), encoding="utf-8"
        )

    write([{**d, "supporting_references": []}])
    with pytest.raises(ValueError):
        apply_decisions(candidate, decisions, out, None)
    write([d, d])
    with pytest.raises(ValueError, match="Duplicate"):
        apply_decisions(candidate, decisions, out, None)
    write([d])
    apply_decisions(candidate, decisions, out, None)
    audit = json.loads(out.read_text(encoding="utf-8"))
    assert audit["accepted_records"][0]["validation_status"] == "review_required"
    with pytest.raises(ValueError, match="immutable"):
        apply_decisions(candidate, decisions, out, None)


def test_approved_search_rejects_unbound_payload(tmp_path: Path) -> None:
    from combustion_atlas.retrieval.__main__ import _load

    path = tmp_path / "forged.json"
    path.write_text(json.dumps({"accepted_records": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate-bound"):
        _load(path, "approved")


def test_numeric_leading_zero_remains_unresolved() -> None:
    row = RawRow(record_number=2, cells={"Test #": "T1", "Calibrated initial O2 % by vol": "037"})
    record = extract_bass_row(
        row,
        investigation_id="SYNTHETIC",
        source_url="https://example.org/source",
        source_sha256="a" * 64,
    )
    assert record.conditions.oxygen_pct is not None
    assert record.conditions.oxygen_pct.value is None
    assert record.conditions.oxygen_pct.original_value == "037"
    assert record.validation_status == "review_required"
