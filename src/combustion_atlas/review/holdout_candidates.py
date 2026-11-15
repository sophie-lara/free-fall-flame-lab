"""Prepare selected, unreviewed CSV records for review in data/review."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from combustion_atlas.artifacts import CandidateBatch, SourceIdentity
from combustion_atlas.ingestion.table_parser import read_csv_losslessly
from combustion_atlas.normalization.extractor import extract_bass_row

from .evidence_schema import EvidenceCandidate

CONDITIONS = {
    "Material",
    "Samle Thickness ",
    "Sample Length ",
    "Sample Width (cm)",
    "Air Flow (cm/s)",
    "Percent O2 (Note 1)",
    "Ignition Power (W)",
    "Ignition Time (s)",
    "Flow Direction",
}
OUTCOMES = {
    "Burn Time (s)",
    "?-g Burn Length",
    "?-g Spread Length",
    "1-g Burn Length",
    "1-g Spread Rate",
}


def prepare(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    selection = json.loads(
        (root / "data/processed/holdout-selection-v1.json").read_text(encoding="utf-8")
    )["rows"]
    bass = []
    saffire = []
    source: SourceIdentity | None = None
    for selected in selection:
        path = (root / selected["source_file"]).resolve()
        if not path.is_relative_to((root / "data/raw").resolve()):
            raise ValueError("Source outside data/raw")
        table = read_csv_losslessly(path)
        if table.sha256 != selected["source_sha256"]:
            raise ValueError("Source checksum mismatch")
        rows = [row for row in table.rows if row.record_number == selected["record_number"]]
        if len(rows) != 1:
            raise ValueError("Selected row not found")
        row = rows[0]
        investigation = selected["investigation_id"]
        url = f"https://psi.nasa.gov/physci/repo/data/investigations/{investigation}"
        if investigation == "PSI-25":
            if row.cells.get("Test #") != selected["source_identity"]:
                raise ValueError("BASS identity mismatch")
            bass.append(
                extract_bass_row(
                    row, investigation_id=investigation, source_url=url, source_sha256=table.sha256
                )
            )
            source = SourceIdentity(
                investigation_id=investigation,
                source_url=url,
                local_path=selected["source_file"],
                sha256=table.sha256,
            )
        elif investigation == "PSI-99":
            if row.cells.get("Sample Number") != selected["source_identity"]:
                raise ValueError("Saffire identity mismatch")
            raw = []
            conditions: dict[str, Any] = {}
            outcomes = []
            settings = {}
            for column, text in row.cells.items():
                provenance = {
                    "source_url": url,
                    "file": path.name,
                    "row": row.record_number,
                    "column": column,
                    "page": None,
                    "table": None,
                    "synthetic": False,
                    "source_sha256": table.sha256,
                }
                cell = {"original_value": text, "original_unit": None, "provenance": provenance}
                raw.append(cell)
                if column in CONDITIONS or column in OUTCOMES:
                    qualifier = (
                        "source_blank"
                        if text == ""
                        else "source_marker"
                        if text and text.strip().casefold() in {"none", "n/a", "null"}
                        else None
                    )
                    entry = {
                        **cell,
                        "value": text if text else None,
                        "unit": None,
                        "qualifier": qualifier,
                        "uncertainty": None,
                    }
                    if column in CONDITIONS:
                        conditions[column] = entry
                    else:
                        outcomes.append({**entry, "outcome_type": column})
                elif column.startswith("Camera"):
                    settings[column] = cell
            candidate = EvidenceCandidate.model_validate(
                {
                    "identity": {
                        "investigation_id": investigation,
                        "test_id": f"SAFFIRE-II-{selected['source_identity']}",
                        "sample_id": selected["source_identity"],
                    },
                    "conditions": conditions,
                    "outcomes": outcomes,
                    "instrument_settings": settings,
                    "extra_metadata": {},
                    "raw_cells": raw,
                    "extraction_confidence": None,
                    "validation_status": "review_required",
                    "human_review_status": "unreviewed",
                    "issues": [
                        {
                            "code": "source_review",
                            "field": "record",
                            "severity": "review",
                            "message": "Source strings await transcription and interpretation "
                            "review.",
                        }
                    ],
                }
            )
            saffire.append(candidate.model_dump(mode="json"))
        else:
            raise ValueError("Unexpected investigation")
    if len(bass) != 2 or len(saffire) != 2 or source is None:
        raise ValueError("Expected two BASS and two Saffire rows")
    batch = CandidateBatch(generated_at=datetime.now(UTC), source=source, records=bass)
    return batch.model_dump(mode="json"), {"records": saffire}


def main() -> None:
    root = Path.cwd().resolve()
    native, evidence = prepare(root)
    targets = [
        (root / "data/review/additional-candidates/holdout-bass.json", native),
        (root / "data/review/holdout-evidence.json", evidence),
    ]
    if any(path.exists() for path, _ in targets):
        raise FileExistsError("Holdout candidate output already exists; preserve review bindings")
    for path, value in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print("Prepared four unreviewed source-bound candidates")


if __name__ == "__main__":
    main()
