"""Explicit BASS-II aliases and classifications; unknown fields remain metadata."""

from __future__ import annotations

from combustion_atlas.artifacts import MappingDecision

IDENTITY_FIELDS = {"test #": "test_id", "sample #": "sample_id"}
CONDITION_FIELDS = {
    "fuel sample material": "conditions.material",
    "calibrated initial o2 % by vol": "conditions.oxygen_pct",
    "initial co2 % by vol": "conditions.measurements.initial_co2_pct",
    "initial co (ppm)": "conditions.measurements.initial_co_ppm",
}
OUTCOME_FIELDS = {
    "calibrated final o2 % by vol": "outcomes.final_oxygen_pct",
    "final co2 % by vol": "outcomes.final_co2_pct",
    "final co (ppm)": "outcomes.final_co_ppm",
}
INSTRUMENT_FIELDS = {"flow restrictor", "fan display", "air display", "radiometer gain"}


def normalized_header(value: str) -> str:
    return " ".join(value.split()).casefold()


def classify_header(header: str) -> MappingDecision:
    key = normalized_header(header)
    if key in IDENTITY_FIELDS:
        return MappingDecision(
            source_field=header, category="identity", canonical_field=IDENTITY_FIELDS[key]
        )
    if key in CONDITION_FIELDS:
        return MappingDecision(
            source_field=header, category="condition", canonical_field=CONDITION_FIELDS[key]
        )
    if key in OUTCOME_FIELDS:
        return MappingDecision(
            source_field=header, category="outcome", canonical_field=OUTCOME_FIELDS[key]
        )
    if key in INSTRUMENT_FIELDS:
        return MappingDecision(
            source_field=header,
            category="instrument_setting",
            note="Retained as a control setting until NASA documents its physical calibration.",
            requires_review=True,
        )
    return MappingDecision(
        source_field=header,
        category="extra_metadata",
        note="No explicit canonical alias; source value is preserved without interpretation.",
    )
