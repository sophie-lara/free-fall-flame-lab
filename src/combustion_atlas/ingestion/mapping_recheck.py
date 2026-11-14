"""Recheck saved mapping regression results without a provider call."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .llm_handoff import SourceBatch
from .mapping_contract import MappedRow, Profile, material_coverage, validate_mapping
from .mapping_runner import REGRESSION


def reassess(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    result = json.loads(raw)
    proposal = MappedRow.model_validate(result["proposal"])
    source = SourceBatch.model_validate(result["source"])
    test_id = result["record"]["test_id"]
    profile: Profile
    if test_id in REGRESSION:
        profile = REGRESSION[test_id]
    else:
        investigation = result["record"]["investigation_id"]
        if investigation not in {"PSI-25", "PSI-99"}:
            raise ValueError("Unsupported holdout investigation")
        profile = "bass_ii" if investigation == "PSI-25" else "saffire_ii"
    issues = validate_mapping(proposal, profile, source) + material_coverage(
        proposal, result.get("deterministic_material_fields", {})
    )
    return {
        "original_result": path.name,
        "original_sha256": hashlib.sha256(raw).hexdigest(),
        "record": result["record"],
        "validation_issues": issues,
        "source_issues": result["source_issues"],
        "unreferenced_source_cells": result["unreferenced_source_cells"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.results.glob("[0-9][0-9].json"))
    if len(paths) not in {3, 4}:
        raise ValueError("Expected three regression results or four holdout results")
    result = {"schema_version": "mapping-recheck-v1", "records": [reassess(p) for p in paths]}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
