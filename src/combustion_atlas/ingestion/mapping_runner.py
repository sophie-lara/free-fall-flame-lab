"""Run the three-row controlled-mapping regression with local spending reservations."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .mapping_contract import (
    MappedRow,
    Profile,
    mapping_request,
    material_coverage,
    propose_mapping,
)
from .pilot_mapping import flex_mapping, reviewed_source_issues
from .pilot_runner import (
    BUDGET,
    INPUT_RATE,
    MAX_OUTPUT,
    MODEL,
    OUTPUT_RATE,
    build,
    deterministic_bass_fields,
)

REGRESSION: dict[str, Profile] = {
    "B1": "bass_ii",
    "FLEX-T13-Ar": "flex_table_13",
    "SAFFIRE-II-2-2": "saffire_ii",
}


def prepare(root: Path, plan: Path) -> list[tuple[dict[str, Any], Any, Profile, Decimal]]:
    selected = []
    for record, source, _, _ in build(root, plan):
        test_id = record["test_id"]
        if test_id not in REGRESSION:
            continue
        profile = REGRESSION[test_id]
        request = mapping_request(profile, source)
        request_bytes = len(json.dumps(request, ensure_ascii=False).encode("utf-8")) + 16384
        allowance = (
            Decimal(request_bytes) * INPUT_RATE + Decimal(MAX_OUTPUT) * OUTPUT_RATE
        ) / 1_000_000
        selected.append((record, source, profile, allowance))
    if len(selected) != len(REGRESSION) or {s[0]["test_id"] for s in selected} != set(REGRESSION):
        raise ValueError("Regression selection is incomplete or duplicated")
    if sum((s[3] for s in selected), Decimal(0)) > BUDGET:
        raise ValueError("Conservative reservation exceeds the pilot budget")
    return selected


def run(
    root: Path,
    plan: Path,
    output: Path,
    *,
    allow_calls: bool = False,
    client: Any = None,
    prepared_requests: list[tuple[dict[str, Any], Any, Profile, Decimal]] | None = None,
    run_metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    requests = prepared_requests if prepared_requests is not None else prepare(root, plan)
    if not requests or len(requests) > 11 or sum((r[3] for r in requests), Decimal(0)) > BUDGET:
        raise ValueError("Request count or budget reservation exceeded")
    summary = {
        "model": MODEL,
        "calls": len(requests),
        "budget_usd": str(BUDGET),
        "reservation_usd": str(sum((x[3] for x in requests), Decimal(0))),
        "dry_run": not allow_calls,
    }
    if not allow_calls:
        return summary
    load_dotenv(root / ".env", override=False)
    output.mkdir(parents=True, exist_ok=False)
    api = client or OpenAI(timeout=60.0, max_retries=0)
    ledger = output / "ledger.jsonl"
    for n, (record, source, profile, allowance) in enumerate(requests, 1):
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"request": n, "status": "reserved", "reserved_usd": str(allowance)})
                + "\n"
            )
        result = propose_mapping(api, MODEL, profile, source)
        source_mappings, mapping_issues = flex_mapping(source, record)
        source_issues = reviewed_source_issues(source, record)
        proposal = MappedRow.model_validate(result["proposal"])
        fields = proposal.fields
        material_fields = deterministic_bass_fields(source, record["investigation_id"])
        result["validation_issues"].extend(material_coverage(proposal, material_fields))
        linked = {index for field in fields for index in field.source_indexes}
        uncovered = [
            {"cell_index": i, "source_column": c.csv_column or c.source_label}
            for i, c in enumerate(source.cells)
            if i not in linked
        ]
        result.update(
            {
                "record": record,
                "source_mappings": source_mappings,
                "run_metadata": run_metadata or {},
                "deterministic_material_fields": material_fields,
                "unreferenced_source_cells": uncovered,
                "source_issues": [
                    issue.model_dump(mode="json") for issue in [*mapping_issues, *source_issues]
                ],
                "request_sha256": hashlib.sha256(
                    json.dumps(
                        mapping_request(profile, source), sort_keys=True, ensure_ascii=False
                    ).encode()
                ).hexdigest(),
            }
        )
        target = output / f"{n:02}.json"
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        lines = [
            f"# Review: {record['test_id']}",
            "",
            "Unreviewed model mapping.",
            "",
            "## Automated issues",
            "",
        ]
        lines.extend(f"- {issue}" for issue in result["validation_issues"])
        lines.extend(f"- {issue['code']}: {issue['message']}" for issue in result["source_issues"])
        lines.extend(
            f"- unreferenced source cell {cell['cell_index']}: {cell['source_column']}"
            for cell in uncovered
        )
        lines += ["", "## Proposed fields", ""]
        lines.extend(
            f"- {f.canonical_field}: {f.value!r} {f.unit or ''}; "
            f"source cells {f.source_indexes}; {f.missingness}; {f.note or ''}"
            for f in fields
        )
        (output / f"{n:02}.review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        usage = result["usage"]
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"request": n, "status": "complete", "usage": usage}) + "\n")
        cost = (
            Decimal(usage["input_tokens"]) * INPUT_RATE
            + Decimal(usage["output_tokens"]) * OUTPUT_RATE
        ) / 1_000_000
        if cost > allowance:
            raise ValueError("Reported token usage exceeded reservation; inspect ledger")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.workspace.resolve(),
                args.plan,
                args.output,
                allow_calls=args.allow_provider_calls,
            )
        )
    )


if __name__ == "__main__":
    main()
