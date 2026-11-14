"""Offline source-cell handoff and checks for proposed table transcription.

This module does not contact a model provider or promote records into the UI.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from combustion_atlas.rag.visual_models import VisualArtifact

from .table_parser import read_csv_losslessly


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SourceCellRef(Strict):
    """One source cell; CSV record numbers and PDF coordinates have distinct bases."""

    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    filename: str
    source_url: str | None = None
    kind: Literal["csv", "pdf_table"]
    csv_record: int | None = Field(default=None, ge=2)
    csv_column: str | None = None
    artifact_id: str | None = None
    physical_page: int | None = Field(default=None, ge=1)
    table_row: int | None = Field(default=None, ge=0)
    table_column: int | None = Field(default=None, ge=0)
    role: Literal["header", "row_header", "data"] | None = None
    row_span: int | None = Field(default=None, ge=1)
    column_span: int | None = Field(default=None, ge=1)
    unit: str | None = None
    uncertainty: str | None = None
    source_label: str | None = None
    text: str | None
    state: Literal["present", "blank", "unreadable"]

    @model_validator(mode="after")
    def validate_location(self) -> Self:
        csv_location = self.csv_record is not None and bool(self.csv_column)
        pdf_location = all(
            v is not None
            for v in (self.artifact_id, self.physical_page, self.table_row, self.table_column)
        )
        if self.kind == "csv" and (
            not csv_location
            or any(
                v is not None
                for v in (self.artifact_id, self.physical_page, self.table_row, self.table_column)
            )
        ):
            raise ValueError("CSV cells require only a record and column")
        if self.kind == "pdf_table" and (
            not pdf_location or self.csv_record is not None or self.csv_column is not None
        ):
            raise ValueError("PDF cells require only an artifact, page, row, and column")
        if (
            (self.state == "blank" and self.text != "")
            or (self.state == "unreadable" and self.text is not None)
            or (self.state == "present" and (self.text is None or self.text == ""))
        ):
            raise ValueError("Cell state does not match source text")
        return self


class SourceBatch(Strict):
    schema_version: Literal["1.0"] = "1.0"
    cells: list[SourceCellRef] = Field(min_length=1)
    context: list[str] = Field(default_factory=list)


class FieldProposal(Strict):
    field: str = Field(min_length=1)
    value: str | float | None
    unit: str | None
    qualifier: str | None
    cell_indexes: list[int]
    review_reason: str | None
    missingness: Literal[
        "reported",
        "source_marker",
        "source_blank",
        "unreadable",
        "not_found_in_source",
        "mapping_uncertain",
        "inferred",
    ] = "reported"


class Proposal(Strict):
    investigation_id: str
    test_id: str
    fields: list[FieldProposal]


class ReviewIssue(Strict):
    field: str
    code: str
    message: str
    source_cells: list[SourceCellRef] = Field(default_factory=list)


def csv_batch(path: Path, record_number: int, source_url: str | None = None) -> SourceBatch:
    table = read_csv_losslessly(path)
    matches = [row for row in table.rows if row.record_number == record_number]
    if len(matches) != 1:
        raise ValueError("CSV record number not found")
    return SourceBatch(
        cells=[
            SourceCellRef(
                source_sha256=table.sha256,
                filename=path.name,
                source_url=source_url,
                kind="csv",
                csv_record=record_number,
                csv_column=column,
                text=text,
                state="blank" if text == "" else "present",
            )
            for column, text in matches[0].cells.items()
        ]
    )


def pdf_batch(artifact: VisualArtifact) -> SourceBatch:
    if artifact.kind != "table" or artifact.table is None:
        raise ValueError("A structured table artifact is required")
    if artifact.review_status == "rejected":
        raise ValueError("Rejected table artifacts cannot be used")
    return SourceBatch(
        cells=[
            SourceCellRef(
                source_sha256=artifact.source_sha256,
                filename=artifact.filename,
                source_url=artifact.source_url,
                kind="pdf_table",
                artifact_id=artifact.artifact_id,
                physical_page=artifact.physical_page,
                table_row=cell.row,
                table_column=cell.column,
                text=cell.text,
                state=cell.state,
                role=cell.role,
                row_span=cell.row_span,
                column_span=cell.column_span,
                unit=cell.unit,
                uncertainty=cell.uncertainty,
            )
            for cell in artifact.table.cells
        ],
        context=[
            f"Artifact review status: {artifact.review_status}",
            artifact.caption,
            *artifact.table.footnotes,
        ],
    )


def check_proposal(batch: SourceBatch, proposal: Proposal) -> list[ReviewIssue]:
    """Check source links and surface declared uncertainty; never certify semantic accuracy."""
    issues: list[ReviewIssue] = []
    seen: set[str] = set()
    if not proposal.fields:
        issues.append(
            ReviewIssue(field="record", code="empty_proposal", message="No fields were proposed.")
        )
    for field in proposal.fields:
        linked = [batch.cells[i] for i in field.cell_indexes if 0 <= i < len(batch.cells)]
        if not field.cell_indexes and field.missingness not in {
            "not_found_in_source",
            "mapping_uncertain",
        }:
            issues.append(
                ReviewIssue(
                    field=field.field,
                    code="missing_source_reference",
                    message="The proposed field has no source reference.",
                )
            )
        if len(linked) != len(field.cell_indexes):
            issues.append(
                ReviewIssue(
                    field=field.field,
                    code="invalid_source_reference",
                    message="One or more cell references do not exist.",
                )
            )
        if field.field in seen:
            issues.append(
                ReviewIssue(
                    field=field.field,
                    code="duplicate_field",
                    message="Multiple proposals target this field.",
                )
            )
        seen.add(field.field)
        if field.review_reason:
            issues.append(
                ReviewIssue(
                    field=field.field,
                    code="model_uncertainty",
                    message=field.review_reason,
                    source_cells=linked,
                )
            )
        if field.missingness in {"inferred", "mapping_uncertain"}:
            issues.append(
                ReviewIssue(
                    field=field.field,
                    code=field.missingness,
                    message="Interpretation requires review.",
                    source_cells=linked,
                )
            )
        for cell in linked:
            expected = (
                "source_blank"
                if cell.state == "blank"
                else "unreadable"
                if cell.state == "unreadable"
                else "source_marker"
                if cell.text is not None
                and cell.text.strip().casefold() in {"n/a", "na", "null", "none"}
                else None
            )
            if expected and field.missingness != expected:
                issues.append(
                    ReviewIssue(
                        field=field.field,
                        code="missingness_mismatch",
                        message=f"Source indicates {expected}; verify proposed status.",
                        source_cells=[cell],
                    )
                )
        if field.value is not None and linked and all(c.state != "present" for c in linked):
            issues.append(
                ReviewIssue(
                    field=field.field,
                    code="unsupported_value",
                    message="A value was proposed from blank or unreadable cells.",
                    source_cells=linked,
                )
            )
        if (
            field.value is not None
            and linked
            and all(
                c.text is not None and c.text.strip().casefold() in {"n/a", "na", "null", "none"}
                for c in linked
            )
            and not (
                field.missingness == "source_marker"
                and isinstance(field.value, str)
                and all(c.text == field.value for c in linked)
            )
        ):
            issues.append(
                ReviewIssue(
                    field=field.field,
                    code="source_missing_marker",
                    message="A value was proposed from source missingness markers.",
                    source_cells=linked,
                )
            )
        if len(linked) == 1 and isinstance(field.value, (float, int)):
            try:
                original_number = float(linked[0].text or "")
            except ValueError:
                pass
            else:
                if math.isfinite(original_number) and not math.isclose(
                    float(field.value), original_number, rel_tol=1e-9, abs_tol=1e-12
                ):
                    issues.append(
                        ReviewIssue(
                            field=field.field,
                            code="numeric_change",
                            message="Proposed number differs from source; verify any conversion.",
                            source_cells=linked,
                        )
                    )
    return issues


def review_markdown(proposal: Proposal, issues: list[ReviewIssue]) -> str:
    lines = [
        "# Ingestion review",
        "",
        f"Investigation: {proposal.investigation_id}",
        f"Test: {proposal.test_id}",
        "",
        f"Issues: {len(issues)}",
        "",
        "These checks do not establish transcription accuracy or human approval.",
        "",
    ]
    for issue in issues:
        lines += [f"## {issue.field} — {issue.code}", "", issue.message, ""]
        for field in proposal.fields:
            if field.field == issue.field:
                lines.append(f"Proposed value: {field.value!r}; unit: {field.unit!r}")
                lines.append("")
        for cell in issue.source_cells:
            location = (
                f"record {cell.csv_record}, column {cell.csv_column}"
                if cell.kind == "csv"
                else f"page {cell.physical_page}, table {cell.artifact_id}, "
                f"row {cell.table_row}, column {cell.table_column}"
            )
            raw_text = json.dumps(cell.text, ensure_ascii=False)
            lines.append(f"- {cell.filename}, {location}: {raw_text}")
        lines.append("")
    return "\n".join(lines)
