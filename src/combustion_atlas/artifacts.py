"""Versioned artifact envelopes shared by command-line workflows."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .normalization.schema import ExperimentRecord

SCHEMA_VERSION = "0.1.0"


class SourceIdentity(BaseModel):
    """Stable identity for a captured source file."""

    investigation_id: str
    source_url: str
    local_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    captured_at: datetime | None = None


class MappingDecision(BaseModel):
    """Auditable disposition of one source field."""

    source_field: str
    category: str
    canonical_field: str | None = None
    note: str | None = None
    requires_review: bool = False


class CandidateBatch(BaseModel):
    """Candidate records and mapping decisions awaiting human review."""

    schema_version: str = SCHEMA_VERSION
    generated_at: datetime
    source: SourceIdentity
    records: list[ExperimentRecord]
    mapping_decisions: list[MappingDecision] = Field(default_factory=list)
