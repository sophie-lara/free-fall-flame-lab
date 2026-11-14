"""Small deterministic checks; scientific review remains a separate workflow."""

from __future__ import annotations

from .schema import ExperimentRecord, ValidationStatus


def validate_candidate(record: ExperimentRecord) -> ExperimentRecord:
    """Flag values needing review while preserving the source record unchanged."""
    messages: list[str] = []
    oxygen = record.conditions.oxygen_pct
    if oxygen and oxygen.value is not None and not 0 <= oxygen.value <= 100:
        messages.append("Initial oxygen is outside the allowed 0-100 percent range.")
    if record.instrument_settings:
        messages.append("Instrument/control settings require scientific interpretation.")
    status = ValidationStatus.REVIEW_REQUIRED if messages else ValidationStatus.VALIDATED
    return record.model_copy(update={"validation_status": status, "validation_messages": messages})
