"""Deterministic table-cell access and pre-import validation for contributed tables.

Embeddings locate a table; exact values must be read from structured cells here,
never from generated prose. This module never transcribes tables.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .store import DocumentStore
from .visual_models import TableCell, TableContent, VisualArtifact
from .visuals import crop_file

NUMERIC = re.compile(r"\d")
UNIT_IN_HEADER = re.compile(r"\(([^()]+)\)\s*$|\[([^\[\]]+)\]\s*$")


def _covers(cell: TableCell, row: int, column: int) -> bool:
    return (
        cell.row <= row < cell.row + cell.row_span
        and cell.column <= column < cell.column + cell.column_span
    )


def resolve_cells(table: TableContent) -> list[dict[str, Any]]:
    """Data cells with their column-header and row-header paths, in reading order.

    Header text is verbatim; spans are honored, so a merged header applies to
    every column it covers. Missing cells keep their state instead of a value.
    """
    headers = [c for c in table.cells if c.role == "header"]
    row_headers = [c for c in table.cells if c.role == "row_header"]
    resolved = []
    for cell in sorted(table.cells, key=lambda c: (c.row, c.column)):
        if cell.role != "data":
            continue
        column_path = [
            h
            for h in sorted(headers, key=lambda h: h.row)
            if h.row < cell.row
            and any(
                _covers(h, h.row, c) for c in range(cell.column, cell.column + cell.column_span)
            )
        ]
        row_path = [
            h
            for h in sorted(row_headers, key=lambda h: h.column)
            if h.column < cell.column
            and any(_covers(h, r, h.column) for r in range(cell.row, cell.row + cell.row_span))
        ]
        resolved.append(
            {
                "row": cell.row,
                "column": cell.column,
                "text": cell.text,
                "state": cell.state,
                "unit": cell.unit or next((h.unit for h in reversed(column_path) if h.unit), None),
                "uncertainty": cell.uncertainty,
                "column_headers": [h.text for h in column_path],
                "row_headers": [h.text for h in row_path],
            }
        )
    return resolved


def find_cells(
    table: TableContent, *, column: str | None = None, row: str | None = None
) -> list[dict[str, Any]]:
    """Case-insensitive substring match on header paths; no fuzzy or numeric coercion."""

    def matches(path: list[str | None], needle: str | None) -> bool:
        return needle is None or any(needle.lower() in (text or "").lower() for text in path)

    return [
        cell
        for cell in resolve_cells(table)
        if matches(cell["column_headers"], column) and matches(cell["row_headers"], row)
    ]


def _table_warnings(artifact: VisualArtifact) -> list[str]:
    table = artifact.table
    if table is None:
        return []
    warnings = []
    header_cells = [c for c in table.cells if c.role == "header"]
    if not header_cells:
        warnings.append("No header cells; values cannot be tied to column meanings")
    for cell in table.cells:
        where = f"cell r{cell.row}c{cell.column}"
        if cell.state == "unreadable" and not (cell.uncertainty or "").strip():
            warnings.append(f"{where}: unreadable without an uncertainty explanation")
        if cell.role == "header" and cell.text and cell.unit is None:
            match = UNIT_IN_HEADER.search(cell.text)
            if match:
                warnings.append(
                    f"{where}: header shows unit '{match.group(1) or match.group(2)}' "
                    "but `unit` is unset"
                )
    for item in resolve_cells(table):
        if item["state"] == "present" and NUMERIC.search(item["text"] or "") and not item["unit"]:
            heading = " / ".join(h or "" for h in item["column_headers"]) or "no header"
            warnings.append(
                f"cell r{item['row']}c{item['column']}: numeric value without a unit "
                f"(column: {heading}); confirm it is dimensionless"
            )
    if artifact.region.scope == "page_context":
        warnings.append("Crop is full-page context, not an isolated table region")
    if artifact.review_status == "reviewed":
        warnings.append("Marked reviewed; confirm the named reviewer checked it against the crop")
    return warnings


def validate_manifest(manifest: Path, *, workspace: Path, database: Path | None) -> dict[str, Any]:
    """Check every line and collect all problems; never writes to the database."""
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        lines = manifest.read_bytes().decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        return {"valid": False, "records": [], "file_errors": [f"Not UTF-8: {exc}"]}
    store = DocumentStore(database) if database and database.is_file() else None
    try:
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            errors: list[str] = []
            warnings: list[str] = []
            artifact = None
            try:
                payload = json.loads(line)
                artifact = VisualArtifact.model_validate(payload)
            except json.JSONDecodeError as exc:
                errors.append(f"Invalid JSON: {exc.msg}")
            except ValidationError as exc:
                errors.extend(
                    f"{'.'.join(str(p) for p in e['loc']) or 'record'}: {e['msg']}"
                    for e in exc.errors()
                )
            if artifact is not None:
                if artifact.artifact_id in seen:
                    errors.append("Duplicate artifact_id in manifest")
                seen.add(artifact.artifact_id)
                if artifact.kind == "table" and artifact.table is None:
                    errors.append("Table records require structured cells")
                if artifact.review_status == "rejected":
                    errors.append("Rejected artifacts cannot be indexed")
                try:
                    crop_file(workspace, artifact)
                except (OSError, ValueError) as exc:
                    errors.append(f"Crop: {exc}")
                if store is not None:
                    page = store.connection.execute(
                        "SELECT sha256, filename FROM pages WHERE source_id=? AND physical_page=?",
                        (artifact.source_id, artifact.physical_page),
                    ).fetchone()
                    if page is None:
                        errors.append(
                            f"Source page {artifact.source_id} p{artifact.physical_page} "
                            "is not in the document index"
                        )
                    elif page["sha256"] != artifact.source_sha256:
                        errors.append("source_sha256 differs from the indexed document")
                    elif page["filename"] != artifact.filename:
                        errors.append(
                            f"filename '{artifact.filename}' differs from indexed "
                            f"'{page['filename']}'"
                        )
                warnings.extend(_table_warnings(artifact))
            records.append(
                {
                    "line": number,
                    "artifact_id": artifact.artifact_id if artifact else None,
                    "kind": artifact.kind if artifact else None,
                    "errors": errors,
                    "warnings": warnings,
                }
            )
    finally:
        if store is not None:
            store.close()
    file_errors = [] if records else ["Manifest contains no records"]
    if database is None or store is None:
        file_errors.append("Document index unavailable; source identity was not checked")
    return {
        "valid": not file_errors and all(not r["errors"] for r in records),
        "records": records,
        "file_errors": file_errors,
    }
