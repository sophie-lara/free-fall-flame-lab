"""Source-scoped mapping and deterministic review rules for pilot evidence."""

from __future__ import annotations

from typing import Any

from .llm_handoff import Proposal, ReviewIssue, SourceBatch

# Scoped to the exact reviewed PDF bytes and Table 13, not all uses of d or k.
FLEX_SHA = "be236c283ffd597bb79a4715fd4b24d296b2b93de1144c676c119b52a3a3ebe9"
BASS_SHA = "71e792bf6b5fb5ea620c5dd70fbbac05515992e12aefcf5dff47312caa48c042"
SAFFIRE_SHA = "3c24390b9ef86f3d1ebaab911a1a3cc95a8759aebf42062371370e6d4b31b8ac"

FLEX_FIELDS = {
    "Ambient": "ambient_diluent_gas",
    "d (mm)": "droplet_diameter",
    "k (mm²/s)": "burning_rate_constant",
    "τres (s)": "fuel_vapor_residence_time",
    "Tf (K)": "flame_temperature",
}


def flex_mapping(
    batch: SourceBatch, record: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[ReviewIssue]]:
    if record.get("investigation_id") != "PSI-69" or record.get("source_sha256") != FLEX_SHA:
        return [], []
    mapped: list[dict[str, Any]] = []
    issues: list[ReviewIssue] = []
    for index, cell in enumerate(batch.cells):
        if (
            cell.source_sha256 != FLEX_SHA
            or cell.physical_page != 76
            or cell.artifact_id != "FLEX-table-13-capture"
        ):
            raise ValueError("FLEX mapping requires the reviewed Table 13 source")
        canonical = FLEX_FIELDS.get(cell.source_label or "")
        if canonical is None:
            continue
        tentative = canonical in {"droplet_diameter", "burning_rate_constant"}
        mapped.append(
            {
                "canonical_field": canonical,
                "source_label": cell.source_label,
                "source_text": cell.text,
                "source_unit": cell.unit,
                "cell_index": index,
                "mapping_status": "proposed" if tentative else "source_label",
                "definition_physical_pages": [64, 76] if tentative else [76],
                "source_sha256": FLEX_SHA,
            }
        )
        if tentative:
            issues.append(
                ReviewIssue(
                    field=canonical,
                    code="unverified_field_mapping",
                    message=(
                        "Proposed interpretation is source-scoped; verify precise table meaning."
                    ),
                    source_cells=[cell],
                )
            )
    return mapped, issues


def reviewed_source_issues(batch: SourceBatch, record: dict[str, Any]) -> list[ReviewIssue]:
    """Retain previously reviewed open questions only for their exact source cells."""
    rules = {
        (BASS_SHA, "B2"): (
            "Calibrated final O2 % by vol",
            "1.6",
            "final_oxygen",
            "Final oxygen interpretation remains under review.",
        ),
        (BASS_SHA, "B4"): (
            "Initial CO (ppm)",
            "-1",
            "initial_co",
            "Negative initial CO interpretation remains under review.",
        ),
        (SAFFIRE_SHA, "SAFFIRE-II-2-4"): (
            "Samle Thickness",
            "037 mm",
            "sample_thickness",
            "Source literal 037 mm remains ambiguous.",
        ),
    }
    rule = rules.get((str(record.get("source_sha256")), str(record.get("test_id"))))
    if rule is None:
        return []
    column, value, field, message = rule
    matches = [
        cell
        for cell in batch.cells
        if cell.source_sha256 == record["source_sha256"]
        and (cell.csv_column or "").strip() == column
        and (cell.text or "").strip() == value
    ]
    if len(matches) != 1:
        raise ValueError("Reviewed question no longer matches the source cell")
    return [
        ReviewIssue(
            field=field, code="reviewed_source_ambiguity", message=message, source_cells=matches
        )
    ]


def coverage_issues(
    batch: SourceBatch, proposal: Proposal, record: dict[str, Any]
) -> list[ReviewIssue]:
    """Identify source cells with no model field reference; identity has a separate location."""
    linked = {index for field in proposal.fields for index in field.cell_indexes}
    issues = []
    for index, cell in enumerate(batch.cells):
        if index in linked:
            continue
        if (cell.csv_column or "").strip().casefold() == "test #" and (
            cell.text or ""
        ).strip() == record.get("test_id"):
            continue
        issues.append(
            ReviewIssue(
                field=cell.csv_column or cell.source_label or str(index),
                code="unmapped_source_cell",
                message="No proposed field references this source cell.",
                source_cells=[cell],
            )
        )
    return issues
