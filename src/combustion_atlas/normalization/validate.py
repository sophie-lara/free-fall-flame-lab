"""Small deterministic checks; scientific review remains a separate workflow."""

from __future__ import annotations

import math

from .schema import ExperimentRecord, ValidationStatus


def validate_candidate(record: ExperimentRecord) -> ExperimentRecord:
    """Flag values needing review while preserving the source record unchanged."""
    messages: list[str] = list(record.validation_messages)
    oxygen = record.conditions.oxygen_pct
    if oxygen and oxygen.value is not None and not 0 <= oxygen.value <= 100:
        messages.append("Initial oxygen is outside the allowed 0-100 percent range.")
    if record.instrument_settings:
        messages.append("Instrument/control settings require scientific interpretation.")
    measurements = list(record.conditions.dimensions.values()) + list(
        record.conditions.measurements.values()
    )
    measurements += [
        m
        for m in (
            record.conditions.oxygen_pct,
            record.conditions.pressure_kpa,
            record.conditions.airflow_cm_s,
            record.conditions.temperature,
        )
        if m
    ]
    measurements += list(record.outcomes)
    for measurement in measurements:
        if measurement.value is not None and not math.isfinite(measurement.value):
            messages.append("Non-finite measurement requires review.")
        if measurement.qualifier == "unparsed_or_qualified":
            messages.append("Qualified or unsupported source value requires review.")
        if measurement.unit == "ppm" and measurement.value is not None and measurement.value < 0:
            messages.append("Negative ppm reading requires source interpretation.")
    status = ValidationStatus.REVIEW_REQUIRED if messages else ValidationStatus.VALIDATED
    if record.validation_status == ValidationStatus.REJECTED:
        status = ValidationStatus.REJECTED
    return record.model_copy(
        update={"validation_status": status, "validation_messages": list(dict.fromkeys(messages))}
    )
