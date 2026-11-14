"""Capture source-bound holdout reviews as a local evaluation reference."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from combustion_atlas.app.server import Workspace
from combustion_atlas.ingestion.table_parser import read_csv_losslessly


def prepare(root: Path) -> dict[str, Any]:
    selection = json.loads((root / "data/processed/holdout-selection-v1.json").read_text(
        encoding="utf-8"))["rows"]
    workspace = Workspace(root)
    native = {(r.investigation_id, r.test_id): r.model_dump(mode="json")
              for r in workspace.records()}
    preserved = {(r["identity"]["investigation_id"], r["identity"]["test_id"]): r
                 for r in workspace.preserved()}
    notes = workspace.notes()
    locked = []
    for item in selection:
        investigation = item["investigation_id"]
        test = item["source_identity"] if investigation == "PSI-25" else (
            f"SAFFIRE-II-{item['source_identity']}"
        )
        key = (investigation, test)
        if (key in native) == (key in preserved):
            raise ValueError(f"Candidate missing or duplicated: {key}")
        candidate = native[key] if key in native else preserved[key]
        candidate_sha = hashlib.sha256(json.dumps(candidate, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        path = (root / item["source_file"]).resolve()
        if not path.is_relative_to((root / "data/raw").resolve()):
            raise ValueError("Source outside data/raw")
        table = read_csv_losslessly(path)
        if table.sha256 != item["source_sha256"]:
            raise ValueError(f"Source checksum mismatch: {key}")
        rows = [r for r in table.rows if r.record_number == item["record_number"]]
        if len(rows) != 1:
            raise ValueError(f"Source row missing: {key}")
        raw = candidate["raw_cells"]
        cells = raw if isinstance(raw, dict) else {
            c["provenance"]["column"]: c["original_value"] for c in raw
        }
        if cells != rows[0].cells:
            raise ValueError(f"Candidate source cells differ: {key}")
        history = [n for n in notes if (n.get("investigation_id"), n.get("test_id")) == key]
        if not history or any(n.get("binding_status") != "matched" or
                              n.get("candidate_fingerprint") != candidate_sha for n in history):
            raise ValueError(f"Review absent or not bound to this candidate: {key}")
        if len({n["decision"] for n in history}) != 1:
            raise ValueError(f"Conflicting review decisions require reconciliation: {key}")
        ordered = sorted(history, key=lambda n: n["saved_at_utc"])
        locked.append({"investigation_id": investigation, "test_id": test,
                       "source_sha256": table.sha256, "record_number": item["record_number"],
                       "candidate_fingerprint": candidate_sha, "candidate": candidate,
                       "review_history": ordered, "latest_review": ordered[-1],
                       "interpretation_status": "open" if ordered[-1]["decision"] ==
                       "needs_research" else "not_scientifically_adjudicated"})
    if len(locked) != 4:
        raise ValueError("Expected four holdout reviews")
    return {"schema_version": "holdout-review-v1", "records": locked,
            "note": "Review notes are drafts; retained open questions are not gold answers."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.workspace.resolve())
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"locked": len(result["records"]), "provider_calls": 0}))


if __name__ == "__main__":
    main()
