"""Filter candidate or approved experiment records."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from combustion_atlas.artifacts import CandidateBatch
from combustion_atlas.io import read_json
from combustion_atlas.normalization.schema import ExperimentRecord
from combustion_atlas.review.workflow import apply_decisions

from .structured import filter_records


def _load(path: Path, scope: str) -> list[ExperimentRecord]:
    payload = read_json(path)
    if scope == "approved":
        if (
            not isinstance(payload, dict)
            or not payload.get("candidate_file")
            or not payload.get("decision_file")
        ):
            raise ValueError("Approved search requires a candidate-bound adjudication audit")
        with tempfile.TemporaryDirectory() as directory:
            replay = Path(directory) / "audit.json"
            apply_decisions(
                Path(payload["candidate_file"]), Path(payload["decision_file"]), replay, None
            )
            verified = read_json(replay)
        if verified != payload:
            raise ValueError("Approved artifact does not match its source decisions")
    values = (
        CandidateBatch.model_validate(payload).records
        if scope == "candidates"
        else payload["accepted_records"]
    )
    return [
        value if isinstance(value, ExperimentRecord) else ExperimentRecord.model_validate(value)
        for value in values
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exact structured experiment filtering")
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--scope", choices=["candidates", "approved"], default="candidates")
    parser.add_argument("--investigation")
    parser.add_argument("--material")
    parser.add_argument("--geometry")
    parser.add_argument("--oxygen-min-pct", type=float)
    parser.add_argument("--oxygen-max-pct", type=float)
    args = parser.parse_args(argv)
    records = filter_records(
        _load(args.artifact, args.scope),
        investigation_id=args.investigation,
        material=args.material,
        geometry=args.geometry,
        oxygen_min_pct=args.oxygen_min_pct,
        oxygen_max_pct=args.oxygen_max_pct,
    )
    print(json.dumps([record.model_dump(mode="json") for record in records], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
