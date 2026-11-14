"""Page- and chunk-level document provenance models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageRecord(BaseModel):
    source_id: str
    investigation_id: str | None = None
    filename: str
    source_url: str | None = None
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    physical_page: int = Field(ge=1)
    text: str
    extraction_warning: str | None = None


class ChunkRecord(BaseModel):
    chunk_id: str
    source_id: str
    investigation_id: str | None = None
    filename: str
    source_url: str | None = None
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    # One-based PDF page; 0 means "no page" (e.g. a CSV record card), never invented.
    physical_page: int = Field(ge=0)
    chunk_index: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    text: str
