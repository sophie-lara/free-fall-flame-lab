"""Lossless table-capture models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RawRow(BaseModel):
    """A CSV row with source strings preserved exactly."""

    record_number: int = Field(ge=2)
    cells: dict[str, str | None]


class RawTable(BaseModel):
    """A captured table and its immutable checksum."""

    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    columns: list[str]
    rows: list[RawRow]
