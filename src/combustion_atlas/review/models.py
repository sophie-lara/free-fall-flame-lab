"""Fingerprinted human decisions and adjudication artifacts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DecisionAction(StrEnum):
    ACCEPT = "accept"
    CORRECT = "correct"
    NEEDS_RESEARCH = "needs_research"
    REJECT = "reject"


class ReviewDecision(BaseModel):
    investigation_id: str
    test_id: str
    candidate_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: DecisionAction | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    rationale: str | None = None
    supporting_references: list[str] = Field(default_factory=list)
    corrected_record: dict[str, Any] | None = None


class DecisionFile(BaseModel):
    schema_version: str = "0.1.0"
    candidate_file: str
    decisions: list[ReviewDecision]
