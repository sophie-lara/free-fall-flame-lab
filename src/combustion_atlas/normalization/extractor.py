"""Deterministic BASS-II candidate extraction from lossless rows."""

from __future__ import annotations

import re

from pydantic import HttpUrl

from combustion_atlas.artifacts import MappingDecision
from combustion_atlas.ingestion.models import RawRow

from .field_mapper import classify_header, normalized_header
from .schema import Conditions, ExperimentRecord, Measurement, OutcomeMeasurement, Provenance
from .validate import validate_candidate

_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _value(cells: dict[str, str | None], normalized_name: str) -> tuple[str, str | None] | None:
    for header, value in cells.items():
        if normalized_header(header) == normalized_name:
            return header, value
    return None


def _number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    match = _NUMBER.search(value.replace(",", ""))
    return float(match.group()) if match else None


def _provenance(source_url: str, source_sha256: str, row: RawRow, column: str) -> Provenance:
    return Provenance(
        source_url=HttpUrl(source_url),
        source_sha256=source_sha256,
        source_locator=f"CSV record {row.record_number}, column {column}",
        record_number=row.record_number,
        column_name=column,
    )


def _measurement(
    *,
    source_url: str,
    source_sha256: str,
    row: RawRow,
    header: str,
    raw: str | None,
    unit: str,
) -> Measurement:
    return Measurement(
        value=_number(raw),
        unit=unit,
        original_value=raw,
        original_unit=unit,
        provenance=_provenance(source_url, source_sha256, row, header),
    )


def extract_bass_row(
    row: RawRow,
    *,
    investigation_id: str,
    source_url: str,
    source_sha256: str,
) -> ExperimentRecord:
    test_cell = _value(row.cells, "test #")
    if test_cell is None or not test_cell[1] or not test_cell[1].strip():
        raise ValueError(f"CSV record {row.record_number} has no Test #")
    sample_cell = _value(row.cells, "sample #")
    material_cell = _value(row.cells, "fuel sample material")
    conditions = Conditions(material_original=material_cell[1] if material_cell else None)
    if material_cell and material_cell[1]:
        raw_material = material_cell[1]
        if re.search(r"\bPMMA\b", raw_material, re.IGNORECASE):
            conditions.material = "PMMA"
        if re.search(r"\bfilm\b", raw_material, re.IGNORECASE):
            conditions.geometry = "film"

    initial_fields = {
        "calibrated initial o2 % by vol": ("oxygen_pct", "%"),
        "initial co2 % by vol": ("initial_co2_pct", "%"),
        "initial co (ppm)": ("initial_co_ppm", "ppm"),
    }
    for source_name, (target, unit) in initial_fields.items():
        cell = _value(row.cells, source_name)
        if cell:
            measurement = _measurement(
                source_url=source_url,
                source_sha256=source_sha256,
                row=row,
                header=cell[0],
                raw=cell[1],
                unit=unit,
            )
            if target == "oxygen_pct":
                conditions.oxygen_pct = measurement
            else:
                conditions.measurements[target] = measurement

    outcomes: list[OutcomeMeasurement] = []
    for source_name, outcome_type, unit in (
        ("calibrated final o2 % by vol", "final_oxygen_pct", "%"),
        ("final co2 % by vol", "final_co2_pct", "%"),
        ("final co (ppm)", "final_co_ppm", "ppm"),
    ):
        cell = _value(row.cells, source_name)
        if cell:
            base = _measurement(
                source_url=source_url,
                source_sha256=source_sha256,
                row=row,
                header=cell[0],
                raw=cell[1],
                unit=unit,
            )
            outcomes.append(OutcomeMeasurement(outcome_type=outcome_type, **base.model_dump()))

    instruments: dict[str, str] = {}
    metadata: dict[str, str] = {}
    for header, raw in row.cells.items():
        decision = classify_header(header)
        if raw is None:
            continue
        if decision.category == "instrument_setting":
            instruments[header] = raw
        elif decision.category == "extra_metadata":
            metadata[header] = raw

    row_provenance = _provenance(source_url, source_sha256, row, test_cell[0])
    record = ExperimentRecord(
        investigation_id=investigation_id,
        test_id=test_cell[1],
        sample_id=sample_cell[1] if sample_cell else None,
        conditions=conditions,
        outcomes=outcomes,
        instrument_settings=instruments,
        extra_metadata=metadata,
        raw_cells=row.cells,
        provenance=[row_provenance],
        extraction_confidence=1.0,
    )
    return validate_candidate(record)


def mapping_decisions(columns: list[str]) -> list[MappingDecision]:
    return [classify_header(column) for column in columns]
