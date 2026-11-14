"""Run-level models that keep raw NASA evidence separate from normalized values."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator


class ValidationStatus(StrEnum):
    """Deterministic state of a candidate record."""

    PENDING = "pending"
    VALIDATED = "validated"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class Provenance(BaseModel):
    """Location and immutable identity of a source value."""

    source_url: HttpUrl
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_locator: str | None = None
    record_number: int | None = Field(default=None, ge=1)
    column_name: str | None = None


class Measurement(BaseModel):
    """A normalized measurement paired with the unmodified source representation."""

    value: float | None = None
    unit: str | None = None
    original_value: str | None = None
    original_unit: str | None = None
    qualifier: str | None = None
    uncertainty: float | None = Field(default=None, ge=0)
    provenance: Provenance


class Conditions(BaseModel):
    """Only experimentally supported pre-ignition conditions belong here."""

    material: str | None = None
    fuel_type: str | None = None
    geometry: str | None = None
    material_original: str | None = None
    dimensions: dict[str, Measurement] = Field(default_factory=dict)
    gravity_regime: str | None = None
    gravity_g: float | None = None
    oxygen_pct: Measurement | None = None
    pressure_kpa: Measurement | None = None
    airflow_cm_s: Measurement | None = None
    temperature: Measurement | None = None
    measurements: dict[str, Measurement] = Field(default_factory=dict)
    ignition_method: str | None = None
    suppressant: str | None = None


class OutcomeMeasurement(Measurement):
    """A post-ignition measured outcome; never use this as a predictor."""

    outcome_type: str = Field(min_length=1)


class ExperimentRecord(BaseModel):
    """One individual experimental test or run."""

    investigation_id: str = Field(min_length=1)
    test_id: str = Field(min_length=1)
    sample_id: str | None = None
    descriptive_name: str | None = None
    conditions: Conditions = Field(default_factory=Conditions)
    outcomes: list[OutcomeMeasurement] = Field(default_factory=list)
    instrument_settings: dict[str, str] = Field(default_factory=dict)
    extra_metadata: dict[str, str] = Field(default_factory=dict)
    raw_cells: dict[str, str | None] = Field(default_factory=dict)
    provenance: list[Provenance] = Field(min_length=1)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    validation_status: ValidationStatus = ValidationStatus.PENDING
    validation_messages: list[str] = Field(default_factory=list)

    @field_validator("investigation_id", "test_id", "sample_id", mode="before")
    @classmethod
    def strip_identity(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value
