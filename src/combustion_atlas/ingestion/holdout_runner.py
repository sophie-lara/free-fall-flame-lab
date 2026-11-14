"""Prepare or run four reviewed CSV holdouts; keep review notes out of requests."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from combustion_atlas.review.holdout_lock import prepare as verify_reviews

from .llm_handoff import csv_batch
from .mapping_contract import Profile, mapping_request
from .mapping_runner import run
from .pilot_runner import BUDGET, INPUT_RATE, MAX_OUTPUT, OUTPUT_RATE

EXPECTED = {("PSI-25", "B6"), ("PSI-25", "B7"),
            ("PSI-99", "2-6"), ("PSI-99", "2-7")}


def prepare(root: Path) -> list[tuple[dict[str, Any], Any, Profile, Decimal]]:
    snapshot_path = root / "data/processed/holdout-reviews-v1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if snapshot != verify_reviews(root):
        raise ValueError("Holdout reviews or source changed after the saved snapshot")
    selection = json.loads((root / "data/processed/holdout-selection-v1.json").read_text(
        encoding="utf-8"))["rows"]
    if {(r["investigation_id"], r["source_identity"]) for r in selection} != EXPECTED:
        raise ValueError("Unexpected holdout selection")
    requests = []
    for entry in selection:
        path = (root / entry["source_file"]).resolve()
        if not path.is_relative_to((root / "data/raw").resolve()):
            raise ValueError("Source outside data/raw")
        source = csv_batch(path, entry["record_number"])
        if source.cells[0].source_sha256 != entry["source_sha256"]:
            raise ValueError("Holdout source changed")
        investigation = entry["investigation_id"]
        identity = entry["source_identity"]
        test_id = identity if investigation == "PSI-25" else f"SAFFIRE-II-{identity}"
        profile: Profile = "bass_ii" if investigation == "PSI-25" else "saffire_ii"
        identity_column = "Test #" if profile == "bass_ii" else "Sample Number"
        if not any(c.csv_column == identity_column and c.text == identity for c in source.cells):
            raise ValueError("Holdout row identity changed")
        record = {"investigation_id": investigation, "test_id": test_id,
                  "source_sha256": entry["source_sha256"], "split": "holdout",
                  "record_number": entry["record_number"]}
        request_bytes = len(json.dumps(mapping_request(profile, source), ensure_ascii=False).encode(
            "utf-8")) + 16384
        allowance = (Decimal(request_bytes) * INPUT_RATE +
                     Decimal(MAX_OUTPUT) * OUTPUT_RATE) / 1_000_000
        requests.append((record, source, profile, allowance))
    if sum((item[3] for item in requests), Decimal(0)) > BUDGET:
        raise ValueError("Holdout reservation exceeds budget")
    return requests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    requests = prepare(root)
    snapshot = root / "data/processed/holdout-reviews-v1.json"
    reference_sha = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    summary = run(root, root / "data/processed/pilot-plan-v1.json", args.output,
                  allow_calls=args.allow_provider_calls, prepared_requests=requests,
                  run_metadata={"reference_sha256": reference_sha})
    summary["reference_sha256"] = reference_sha
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
