import json
from pathlib import Path

import pytest

from combustion_atlas.ingestion.llm_handoff import (
    FieldProposal,
    Proposal,
    check_proposal,
    csv_batch,
    pdf_batch,
    review_markdown,
)
from combustion_atlas.rag.visual_models import VisualArtifact


def test_csv_source_preserves_values_and_checks_links(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("Sample,Thickness,Marker\nA,037,n/a\nB,,  \n", encoding="utf-8")
    batch = csv_batch(source, 2)
    assert [c.text for c in batch.cells] == ["A", "037", "n/a"]
    assert batch.cells[1].csv_record == 2
    assert csv_batch(source, 3).cells[1].state == "blank"
    assert csv_batch(source, 3).cells[2].text == "  "
    proposal = Proposal(
        investigation_id="test",
        test_id="A",
        fields=[
            FieldProposal(
                field="thickness",
                value=0.37,
                unit="mm",
                qualifier=None,
                cell_indexes=[1],
                review_reason="Possible missing decimal",
            ),
            FieldProposal(
                field="other",
                value=3,
                unit=None,
                qualifier=None,
                cell_indexes=[42],
                review_reason=None,
            ),
        ],
    )
    issues = check_proposal(batch, proposal)
    assert [i.code for i in issues] == [
        "model_uncertainty",
        "numeric_change",
        "invalid_source_reference",
    ]
    assert '"037"' in review_markdown(proposal, issues)
    assert json.loads(batch.model_dump_json())["cells"][2]["text"] == "n/a"


def test_pdf_artifact_preserves_cell_layout_and_footnotes() -> None:
    sha = "a" * 64
    artifact = VisualArtifact.model_validate(
        {
            "artifact_id": "table-1",
            "kind": "table",
            "source_id": sha[:16],
            "source_sha256": sha,
            "filename": "source.pdf",
            "physical_page": 3,
            "label": "1",
            "caption": "Table 1",
            "crop_path": "data/processed/visuals/a.png",
            "crop_sha256": "b" * 64,
            "region": {
                "page_width": 100,
                "page_height": 100,
                "x0": 0,
                "top": 0,
                "x1": 100,
                "bottom": 100,
            },
            "table": {
                "rows": 1,
                "columns": 2,
                "cells": [
                    {"row": 0, "column": 0, "text": "Fuel", "role": "header"},
                    {"row": 0, "column": 1, "text": None, "state": "unreadable"},
                ],
                "footnotes": ["Values are nominal."],
            },
        }
    )
    batch = pdf_batch(artifact)
    assert batch.cells[0].role == "header"
    assert batch.cells[1].state == "unreadable"
    assert batch.cells[1].artifact_id == "table-1"
    assert batch.context == ["Artifact review status: unreviewed", "Table 1", "Values are nominal."]
    proposal = Proposal(
        investigation_id="i",
        test_id="t",
        fields=[
            FieldProposal(
                field="fuel",
                value="paper",
                unit=None,
                qualifier=None,
                cell_indexes=[1],
                review_reason=None,
            )
        ],
    )
    assert "unsupported_value" in {issue.code for issue in check_proposal(batch, proposal)}
    with pytest.raises(ValueError, match="Rejected"):
        pdf_batch(artifact.model_copy(update={"review_status": "rejected"}))
