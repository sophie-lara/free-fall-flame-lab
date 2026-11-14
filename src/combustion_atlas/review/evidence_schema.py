"""Versioned review evidence values for mixed scientific source formats."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class EvidenceLocation(EvidenceModel):
    source_url: str
    file: str
    row: int = Field(ge=1)
    column: str
    page: int | None = Field(default=None, ge=1)
    table: str | None = None
    synthetic: bool = False
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SourceCell(EvidenceModel):
    original_value: str | None
    original_unit: str | None = None
    provenance: EvidenceLocation


class EvidenceValue(SourceCell):
    value: float | str | None
    unit: str | None = None
    qualifier: str | None = None
    uncertainty: float | str | None = None


class EvidenceOutcome(EvidenceValue):
    outcome_type: str


class EvidenceIdentity(EvidenceModel):
    investigation_id: str
    test_id: str
    sample_id: str | None = None


class EvidenceIssue(EvidenceModel):
    code: str
    field: str
    message: str
    severity: Literal["review", "reject"]


class EvidenceCandidate(EvidenceModel):
    identity: EvidenceIdentity
    conditions: dict[str, EvidenceValue]
    outcomes: list[EvidenceOutcome]
    instrument_settings: dict[str, SourceCell]
    extra_metadata: dict[str, SourceCell]
    raw_cells: list[SourceCell]
    extraction_confidence: float | None
    validation_status: Literal["pending", "validated", "review_required", "rejected"]
    human_review_status: Literal["unreviewed", "accepted", "corrected"]
    issues: list[EvidenceIssue]
