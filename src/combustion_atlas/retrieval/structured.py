"""Exact filtering over candidate or adjudicated run-level records."""

from __future__ import annotations

from collections.abc import Iterable

from combustion_atlas.normalization.schema import ExperimentRecord


def _matches_text(actual: str | None, expected: str | None) -> bool:
    return expected is None or (
        actual is not None and actual.strip().casefold() == expected.strip().casefold()
    )


def _in_range(value: float | None, minimum: float | None, maximum: float | None) -> bool:
    if minimum is None and maximum is None:
        return True
    if value is None:
        return False
    return (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def filter_records(
    records: Iterable[ExperimentRecord],
    *,
    investigation_id: str | None = None,
    material: str | None = None,
    geometry: str | None = None,
    oxygen_min_pct: float | None = None,
    oxygen_max_pct: float | None = None,
) -> list[ExperimentRecord]:
    results = []
    for record in records:
        oxygen = record.conditions.oxygen_pct
        if not _matches_text(record.investigation_id, investigation_id):
            continue
        if not _matches_text(record.conditions.material, material):
            continue
        if not _matches_text(record.conditions.geometry, geometry):
            continue
        if not _in_range(
            oxygen.value if oxygen and oxygen.unit == "%" else None, oxygen_min_pct, oxygen_max_pct
        ):
            continue
        results.append(record)
    return results
