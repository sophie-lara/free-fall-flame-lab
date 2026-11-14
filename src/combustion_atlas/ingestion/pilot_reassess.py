"""Reapply local checks to saved pilot responses without model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .llm_handoff import Proposal, ReviewIssue, SourceBatch, check_proposal
from .pilot_mapping import coverage_issues, flex_mapping, reviewed_source_issues
from .pilot_runner import deterministic_bass_fields, identity_issue


def reassess(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    result = json.loads(raw)
    record = result["record"]
    batch = SourceBatch.model_validate(result["source"])
    proposal = Proposal.model_validate(result["proposal"])
    mapped, mapping_issues = flex_mapping(batch, record)
    issues = (
        check_proposal(batch, proposal)
        + mapping_issues
        + reviewed_source_issues(batch, record)
        + coverage_issues(batch, proposal, record)
    )
    identity = identity_issue(record, proposal)
    if identity:
        issues.append(
            ReviewIssue(
                field="identity", code=identity, message="Model identity requires verification."
            )
        )
    return {
        "original_result": path.name,
        "original_result_sha256": hashlib.sha256(raw).hexdigest(),
        "record": record,
        "source_mappings": mapped,
        "deterministic_material_fields": deterministic_bass_fields(
            batch, record["investigation_id"]
        ),
        "issues": [issue.model_dump(mode="json") for issue in issues],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.results.glob("[0-9][0-9].json"))
    if len(paths) != 11:
        raise ValueError("Expected eleven complete pilot responses")
    values = [reassess(path) for path in paths]
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(
            {"schema_version": "pilot-reassessment-v1", "records": values},
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")
    print(json.dumps({"reassessed": len(values), "provider_calls": 0}))


if __name__ == "__main__":
    main()
