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
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        columns = list(reader.fieldnames)
        rows = [
            RawRow(record_number=index, cells={column: row.get(column) for column in columns})
            for index, row in enumerate(reader, start=2)
        ]
    return RawTable(path=str(path), sha256=sha256_file(path), columns=columns, rows=rows)
