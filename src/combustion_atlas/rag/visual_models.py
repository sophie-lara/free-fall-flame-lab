"""Versioned exchange contract for figure extraction and independently produced tables."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PageRegion(StrictModel):
    """PDF points, origin at the top-left; not image pixels."""

    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    x0: float = Field(ge=0)
    top: float = Field(ge=0)
    x1: float = Field(gt=0)
    bottom: float = Field(gt=0)
    scope: Literal["page_context", "isolated"] = "page_context"

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if not (
            self.x0 < self.x1 <= self.page_width and self.top < self.bottom <= self.page_height
        ):
            raise ValueError("Region must be a nonempty rectangle within the page")
        return self


class TableCell(StrictModel):
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    role: Literal["header", "row_header", "data"] = "data"
    text: str | None
    state: Literal["present", "blank", "unreadable"] = "present"
    unit: str | None = None
    uncertainty: str | None = None

    @model_validator(mode="after")
    def missingness(self) -> Self:
        if self.state == "blank" and self.text != "":
            raise ValueError("A blank source cell must preserve an empty string")
        if self.state == "unreadable" and self.text is not None:
            raise ValueError("Unreadable text must be null; record partial readings in uncertainty")
        if self.state == "present" and (self.text is None or not self.text.strip()):
            raise ValueError("A present cell must have source text")
        return self


class TableContent(StrictModel):
    rows: int = Field(ge=1)
    columns: int = Field(ge=1)
    cells: list[TableCell] = Field(min_length=1)
    footnotes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def layout(self) -> Self:
        occupied: set[tuple[int, int]] = set()
        for cell in self.cells:
            if (
                cell.row + cell.row_span > self.rows
                or cell.column + cell.column_span > self.columns
            ):
                raise ValueError("Cell span exceeds table dimensions")
            for r in range(cell.row, cell.row + cell.row_span):
                for c in range(cell.column, cell.column + cell.column_span):
                    if (r, c) in occupied:
                        raise ValueError("Overlapping table cells")
                    occupied.add((r, c))
        if len(occupied) != self.rows * self.columns:
            raise ValueError("Every table cell needs explicit source or missingness state")
        return self


class VisualArtifact(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    artifact_id: str = Field(pattern=r"^[A-Za-z0-9:._-]+$")
    kind: Literal["figure", "table"]
    source_id: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    filename: str
    source_url: str | None = None
    investigation_id: str | None = None
    physical_page: int = Field(ge=1)
    printed_page: str | None = None
    label: str = Field(min_length=1)
    caption: str
    region: PageRegion
    crop_path: str
    crop_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    description: str = ""
    visible_labels: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    method: Literal["caption_only", "openai_vision", "manual", "table_parser"] = "caption_only"
    model: str | None = None
    prompt_version: str | None = None
    review_status: Literal["unreviewed", "reviewed", "rejected"] = "unreviewed"
    reviewer: str | None = None
    table: TableContent | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.source_id != self.source_sha256[:16]:
            raise ValueError("source_id must equal the first 16 source SHA-256 characters")
        path = PurePosixPath(self.crop_path)
        if path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".png":
            raise ValueError("crop_path must be a safe relative POSIX PNG path")
        if not self.crop_path.startswith("data/processed/visuals/"):
            raise ValueError("Place crops under data/processed/visuals/")
        if self.kind == "figure" and self.table is not None:
            raise ValueError("A figure cannot contain table transcription")
        if self.review_status == "reviewed" and not (self.reviewer and self.reviewer.strip()):
            raise ValueError("Reviewed artifacts require a reviewer")
        if self.method == "openai_vision" and not (self.model and self.prompt_version):
            raise ValueError("Vision output must identify its model and prompt version")
        return self

    def fingerprint(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def retrieval_text(self) -> str:
        parts = [
            f"{self.kind.title()} {self.label}: {self.caption}",
            f"Extraction: {self.method}; review status: {self.review_status}.",
            "Generated descriptions are interpretations, not verified measurements.",
            self.description,
        ]
        parts.extend(f"Visible label: {label}" for label in self.visible_labels)
        parts.extend(f"Uncertainty: {note}" for note in self.uncertainties)
        if self.table:
            # Explicit row/column, role, span and raw values survive text serialization.
            parts.append(json.dumps(self.table.model_dump(mode="json"), ensure_ascii=False))
        return "\n".join(parts)
