"""Prepare bounded, explicit source CSV batches using the controlled mapping contract."""

from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from .llm_handoff import SourceBatch, csv_batch
from .mapping_contract import Profile, mapping_request
from .mapping_runner import run
from .pilot_runner import BUDGET, INPUT_RATE, MAX_OUTPUT, OUTPUT_RATE
from .table_parser import read_csv_losslessly

BASS_ID = r"[BFMOPT][0-9]+[a-z]?"
SAFFIRE_ID = r"2-[0-9]+"


def saffire_context(csv: Path, expected_sha: str) -> list[str]:
    """Capture all source note rows, with record locations and original text."""
    table = read_csv_losslessly(csv)
    if table.sha256 != expected_sha:
        raise ValueError("Saffire source changed while reading notes")
    context = []
    for row in table.rows:
        label = row.cells.get("Sample Number") or ""
        if re.match(r"^\s*Note\s+\d+\b", label, re.IGNORECASE):
            context.append(
                json.dumps(
                    {
                        "source_record_number": row.record_number,
                        "source_sha256": table.sha256,
                        "original_cells": row.cells,
                    },
                    ensure_ascii=False,
                )
            )
    return context


def prepare(
    root: Path, csv: Path, investigation: str, record_numbers: list[int]
) -> list[tuple[dict[str, Any], SourceBatch, Profile, Decimal]]:
    source_path = csv.resolve()
    if not source_path.is_relative_to((root / "data/raw").resolve()):
        raise ValueError("CSV must be inside the workspace data/raw directory")
    if investigation not in {"PSI-25", "PSI-99"}:
        raise ValueError("Only BASS-II and Saffire-II CSV sources are supported")
    if not 1 <= len(record_numbers) <= 11 or len(set(record_numbers)) != len(record_numbers):
        raise ValueError("Select one to eleven distinct CSV record numbers")
    profile: Profile = "bass_ii" if investigation == "PSI-25" else "saffire_ii"
    column = "Test #" if profile == "bass_ii" else "Sample Number"
    url = f"https://psi.nasa.gov/physci/repo/data/investigations/{investigation}"
    requests = []
    for number in record_numbers:
        source = csv_batch(source_path, number, url)
        candidates = [c.text for c in source.cells if c.csv_column == column]
        if len(candidates) != 1 or candidates[0] is None:
            raise ValueError("Record identity column missing")
        identifier = candidates[0].strip()
        if not re.fullmatch(
            BASS_ID if profile == "bass_ii" else SAFFIRE_ID, identifier, re.IGNORECASE
        ):
            raise ValueError(f"Record {number} is not a supported experiment row")
        if profile == "saffire_ii":
            source.context.extend(saffire_context(source_path, source.cells[0].source_sha256))
        test_id = identifier if profile == "bass_ii" else f"SAFFIRE-II-{identifier}"
        record = {
            "investigation_id": investigation,
            "test_id": test_id,
            "source_sha256": source.cells[0].source_sha256,
            "record_number": number,
            "source_file": source_path.relative_to(root).as_posix(),
            "split": "unreviewed",
        }
        request_size = (
            len(json.dumps(mapping_request(profile, source), ensure_ascii=False).encode("utf-8"))
            + 16384
        )
        allowance = (
            Decimal(request_size) * INPUT_RATE + Decimal(MAX_OUTPUT) * OUTPUT_RATE
        ) / 1_000_000
        requests.append((record, source, profile, allowance))
    if len({r[0]["test_id"] for r in requests}) != len(requests):
        raise ValueError("Duplicate source identities")
    if len({r[0]["source_sha256"] for r in requests}) != 1:
        raise ValueError("Source changed during batch preparation")
    if sum((r[3] for r in requests), Decimal(0)) > BUDGET:
        raise ValueError("Batch exceeds the budget reservation")
    return requests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--investigation", choices=["PSI-25", "PSI-99"], required=True)
    parser.add_argument("--records", type=int, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    requests = prepare(root, args.csv, args.investigation, args.records)
    summary = run(
        root,
        root / "data/processed/pilot-plan-v1.json",
        args.output,
        allow_calls=args.allow_provider_calls,
        prepared_requests=requests,
    )
    summary["selected_records"] = [item[0]["test_id"] for item in requests]
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
