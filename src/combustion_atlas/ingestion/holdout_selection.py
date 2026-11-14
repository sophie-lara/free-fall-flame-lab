"""Prepare a source-bound list of unreviewed CSV rows for future evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .table_parser import read_csv_losslessly

SELECTION = {
    "PSI-25": ("PSI-25_Experimental table_BASS-II.csv", "Test #", ("B6", "B7")),
    "PSI-99": ("PSI-99_Experimental table_SAFFIRE-2.csv", "Sample Number", ("2-6", "2-7")),
}


def prepare(root: Path) -> dict[str, object]:
    reviewed = json.loads((root / "data/processed/reviewed-evidence-v1.json").read_text(
        encoding="utf-8"))["records"]
    prior = {(r["investigation_id"], r["test_id"]) for r in reviewed}
    selected = []
    for investigation, (filename, column, ids) in SELECTION.items():
        path = root / "data/raw/preserved-review" / filename
        table = read_csv_losslessly(path)
        for test_id in ids:
            if ((investigation, test_id) in prior or
                    (investigation, f"SAFFIRE-II-{test_id}") in prior):
                raise ValueError("Selected row was already reviewed")
            rows = [row for row in table.rows if (row.cells.get(column) or "").strip() == test_id]
            if len(rows) != 1:
                raise ValueError("Selected source identity is missing or ambiguous")
            selected.append({"investigation_id": investigation, "source_identity": test_id,
                             "source_file": path.relative_to(root).as_posix(),
                             "source_sha256": table.sha256, "record_number": rows[0].record_number,
                             "review_status": "not_reviewed", "role": "candidate_holdout"})
    return {"schema_version": "holdout-selection-v1", "rows": selected,
            "flex": "No independently reviewed unused FLEX row is available here.",
            "evaluation_ready": False,
            "note": "Manual review and a locked reference are required before evaluation."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = prepare(args.workspace.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
