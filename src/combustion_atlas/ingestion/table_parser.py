"""Lossless CSV capture used before any semantic mapping."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .models import RawRow, RawTable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv_losslessly(path: Path, *, encoding: str = "utf-8-sig") -> RawTable:
    """Read a CSV without trimming, coercing, or filling source cells."""
    with path.open(newline="", encoding=encoding) as stream:
        reader = csv.reader(stream, strict=True)
        columns = next(reader, [])
        if not columns or any(not c.strip() for c in columns):
            raise ValueError(f"CSV has no header: {path}")
        normalized = [" ".join(c.split()).casefold() for c in columns]
        if len(normalized) != len(set(normalized)):
            raise ValueError("CSV contains duplicate or ambiguous headers")
        rows = []
        for index, values in enumerate(reader, start=2):
            if len(values) != len(columns):
                raise ValueError(f"CSV record {index} has the wrong number of cells")
            rows.append(RawRow(record_number=index, cells=dict(zip(columns, values, strict=True))))
    return RawTable(path=str(path), sha256=sha256_file(path), columns=columns, rows=rows)
