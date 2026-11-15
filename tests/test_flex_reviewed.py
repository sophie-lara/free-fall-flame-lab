"""FLEX promotion to reviewed evidence: background rows, definitions, planned kind."""

import json

import pytest

from combustion_atlas.ingestion import flex_pdf_run as f
from combustion_atlas.review.evidence_schema import EvidenceCandidate
from combustion_atlas.review.flex_reviewed import _symbol, background_candidates, promote


def table14() -> f.TableExtraction:
    def cell(row, column, text, role="data"):
        return f.ExtractedCell(
            page=80,
            row=row,
            column=column,
            row_span=1,
            column_span=1,
            role=role,
            text=text,
            state="present",
            uncertainty=None,
        )

    cells = [
        cell(0, 0, "Inert", "header"),
        cell(0, 1, "β", "header"),
        cell(0, 2, "D_IO (cm²/s)", "header"),
        cell(1, 0, "He"),
        cell(1, 1, "0.24"),
        cell(1, 2, "10.3"),
    ]
    return f.TableExtraction(
        label="14",
        caption="Table 14: Gas-phase oxygen transport data.",
        header_notes=[],
        rows=2,
        columns=3,
        cells=cells,
        footnotes=[],
        context_flags=[],
        uncertainties=[],
    )


def test_symbol_takes_leading_token() -> None:
    assert _symbol("D_IO (cm²/s)") == "D_IO"
    assert _symbol("Le_O (D_O)") == "Le_O"
    assert _symbol("β") == "β"


def test_background_rows_keep_cells_verbatim_with_definition_notes() -> None:
    records = background_candidates(
        table14(), "14", {"β": "Soret transport factor", "D_IO": "binary diffusion"}, "reviewer"
    )
    assert [r["identity"]["test_id"] for r in records] == ["FLEX-T14-He"]
    fields = records[0]["additional_fields"]
    assert fields["β"]["value"] == "0.24" and fields["β"]["provenance"]["page"] == 80
    assert fields["β"]["notes"][0]["kind"] == "definition"
    assert "binary diffusion" in fields["D_IO (cm²/s)"]["notes"][0]["text"]
    assert fields["Inert"]["notes"] == []
    assert records[0]["conditions"] == {}  # never mapped into canonical fields
    EvidenceCandidate.model_validate(records[0])


def test_promotion_requires_a_recorded_decision(tmp_path) -> None:
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps({"schema_version": "flex-table-review-v1", "tables": {}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="no promotion decision"):
        promote(tmp_path, review, tmp_path / "matrix.json")
