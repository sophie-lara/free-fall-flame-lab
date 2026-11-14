"""Create candidate normalized records and a Markdown review report."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from combustion_atlas.artifacts import CandidateBatch, SourceIdentity
from combustion_atlas.ingestion import read_csv_losslessly
from combustion_atlas.io import write_json

from .extractor import extract_bass_row, mapping_decisions
from .field_mapper import normalized_header
from .report import render_mapping_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize a bounded BASS-II CSV batch")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--investigation-id", required=True)
    parser.add_argument("--test-ids", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    table = read_csv_losslessly(args.csv)
    wanted = {value.casefold() for value in args.test_ids or []}
    rows = []
    for row in table.rows:
        test_value = next(
            (value for header, value in row.cells.items() if normalized_header(header) == "test #"),
            None,
        )
        if not wanted or (test_value and test_value.strip().casefold() in wanted):
            rows.append(row)
    records = [
        extract_bass_row(
            row,
            investigation_id=args.investigation_id,
            source_url=args.source_url,
            source_sha256=table.sha256,
        )
        for row in rows
    ]
    batch = CandidateBatch(
        generated_at=datetime.now(UTC),
        source=SourceIdentity(
            investigation_id=args.investigation_id,
            source_url=args.source_url,
            local_path=str(args.csv),
            sha256=table.sha256,
        ),
        records=records,
        mapping_decisions=mapping_decisions(table.columns),
    )
    write_json(args.output, batch.model_dump(mode="json"))
    report_path = args.output.with_suffix(".md")
    report_path.write_text(render_mapping_report(batch), encoding="utf-8")
    print(f"Wrote {len(records)} candidate records to {args.output}")
    print(f"Wrote review queue to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
