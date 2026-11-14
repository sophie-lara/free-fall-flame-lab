"""Plan and safely execute source-bound CSV batches under a cumulative reservation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
from pathlib import Path
from typing import Any

from combustion_atlas.app.server import Workspace

from .csv_batch_runner import BASS_ID, SAFFIRE_ID, prepare
from .mapping_contract import mapping_request
from .mapping_runner import run
from .pilot_runner import MODEL
from .table_parser import read_csv_losslessly

VERSION = "full-csv-plan-v1"
CODE_FILES = (
    "src/combustion_atlas/ingestion/csv_batch_runner.py",
    "src/combustion_atlas/ingestion/llm_handoff.py",
    "src/combustion_atlas/ingestion/llm_transcribe.py",
    "src/combustion_atlas/ingestion/models.py",
    "src/combustion_atlas/ingestion/mapping_contract.py",
    "src/combustion_atlas/ingestion/mapping_runner.py",
    "src/combustion_atlas/ingestion/pilot_mapping.py",
    "src/combustion_atlas/ingestion/pilot_runner.py",
    "src/combustion_atlas/ingestion/full_csv_run.py",
    "src/combustion_atlas/ingestion/table_parser.py",
    "src/combustion_atlas/normalization/extractor.py",
    "src/combustion_atlas/normalization/field_mapper.py",
    "src/combustion_atlas/normalization/schema.py",
    "src/combustion_atlas/normalization/validate.py",
)


def environment(root: Path) -> dict[str, Any]:
    return {
        "code_sha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in CODE_FILES},
        "packages": {p: version(p) for p in ("openai", "pydantic", "pypdf")},
        "python": sys.version,
    }


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def existing_candidates(workspace: Workspace) -> dict[tuple[str, str], set[str]]:
    existing: dict[tuple[str, str], set[str]] = {}
    for record in workspace.records():
        key = (record.investigation_id, record.test_id)
        existing.setdefault(key, set()).update(p.source_sha256 for p in record.provenance)
    for evidence in workspace.preserved():
        key = (evidence["identity"]["investigation_id"], evidence["identity"]["test_id"])
        existing.setdefault(key, set()).update(
            c["provenance"]["source_sha256"] for c in evidence.get("raw_cells", [])
        )
    return existing


def create_plan(root: Path, paths: dict[str, Path], budget: Decimal) -> dict[str, Any]:
    if not budget.is_finite() or budget <= 0:
        raise ValueError("Budget must be a positive finite amount")
    existing = existing_candidates(Workspace(root))
    records: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for investigation in ("PSI-25", "PSI-99"):
        path = paths[investigation].resolve()
        if not path.is_relative_to((root / "data/raw").resolve()):
            raise ValueError("Source must be inside data/raw")
        table = read_csv_losslessly(path)
        column = "Test #" if investigation == "PSI-25" else "Sample Number"
        pattern = BASS_ID if investigation == "PSI-25" else SAFFIRE_ID
        sources.append(
            {
                "investigation_id": investigation,
                "path": path.relative_to(root).as_posix(),
                "sha256": table.sha256,
                "records": len(table.rows),
            }
        )
        seen: set[str] = set()
        for row in table.rows:
            identity = (row.cells.get(column) or "").strip()
            if not re.fullmatch(pattern, identity, re.IGNORECASE):
                kind = "source_note" if re.match(r"^Note\s+\d+\b", identity, re.I) else "non_run"
                excluded.append(
                    {
                        "investigation_id": investigation,
                        "record_number": row.record_number,
                        "identity": identity,
                        "reason": kind,
                    }
                )
                continue
            test_id = identity if investigation == "PSI-25" else f"SAFFIRE-II-{identity}"
            if test_id.casefold() in seen:
                raise ValueError(f"Duplicate source identity: {test_id}")
            seen.add(test_id.casefold())
            if (investigation, test_id) in existing:
                if existing[(investigation, test_id)] != {table.sha256}:
                    raise ValueError("Existing candidate identity refers to a different source")
                excluded.append(
                    {
                        "investigation_id": investigation,
                        "record_number": row.record_number,
                        "identity": identity,
                        "reason": "existing_review_candidate",
                    }
                )
                continue
            request = prepare(root, path, investigation, [row.record_number])[0]
            record, batch, profile, allowance = request
            records.append(
                {
                    "record": record,
                    "profile": profile,
                    "reservation_usd": str(allowance),
                    "request_sha256": digest(mapping_request(profile, batch)),
                }
            )
    total = sum((Decimal(r["reservation_usd"]) for r in records), Decimal(0))
    if total > budget:
        raise ValueError(f"Conservative reservation {total} exceeds selected total budget")
    return {
        "schema_version": VERSION,
        "model": MODEL,
        "budget_usd": str(budget),
        "environment": environment(root),
        "reservation_usd": str(total),
        "sources": sources,
        "records": records,
        "excluded": excluded,
        "note": "Candidate records and model output are unreviewed.",
    }


def rebuild(root: Path, plan: dict[str, Any]) -> list[tuple[Any, ...]]:
    if plan.get("schema_version") != VERSION or plan.get("model") != MODEL:
        raise ValueError("Unsupported plan or model")
    if plan.get("environment") != environment(root):
        raise ValueError("Pipeline code or provider library changed; create a new plan")
    try:
        budget = Decimal(plan["budget_usd"])
        if not budget.is_finite() or budget <= 0:
            raise ValueError("Invalid plan budget")
    except (KeyError, InvalidOperation) as exc:
        raise ValueError("Invalid plan budget") from exc
    sources = {s["investigation_id"]: s for s in plan["sources"]}
    if set(sources) != {"PSI-25", "PSI-99"}:
        raise ValueError("Invalid source list")
    for source in sources.values():
        path = (root / source["path"]).resolve()
        if not path.is_relative_to((root / "data/raw").resolve()):
            raise ValueError("Source outside data/raw")
        if read_csv_losslessly(path).sha256 != source["sha256"]:
            raise ValueError("A planned source has changed")
    prepared = []
    keys = set()
    existing = existing_candidates(Workspace(root))
    for item in plan["records"]:
        r = item["record"]
        if (r["investigation_id"], r["test_id"]) in existing:
            raise ValueError(
                "A planned identity was added to the review workspace; create a new plan"
            )
        key = (r["investigation_id"], r["record_number"])
        if key in keys:
            raise ValueError("Duplicate source row in plan")
        keys.add(key)
        source = sources.get(r["investigation_id"])
        if source is None or r["source_file"] != source["path"]:
            raise ValueError("Record source does not match plan")
        request = prepare(root, root / source["path"], r["investigation_id"], [r["record_number"]])[
            0
        ]
        record, batch, profile, allowance = request
        if (
            record != r
            or profile != item["profile"]
            or str(allowance) != item["reservation_usd"]
            or digest(mapping_request(profile, batch)) != item["request_sha256"]
        ):
            raise ValueError(
                "Request, context, price assumption or source changed; create a new plan"
            )
        prepared.append(request)
    total = sum((r[3] for r in prepared), Decimal(0))
    if not prepared or total > budget or str(total) != plan["reservation_usd"]:
        raise ValueError("Invalid plan reservation")
    return prepared


def append_event(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def write_review_report(target: Path, plan: dict[str, Any]) -> None:
    """Summarize completed rows; absence of flags is not approval."""
    rows = []
    for path in sorted(target.glob("row-*/01.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        issues = [item for item in data.get("validation_issues", [])
                  if item != "instrument_settings_require_interpretation"]
        issues.extend(f"{item['code']}: {item['message']}" for item in
                      data.get("source_issues", []))
        issues.extend(f"Unreferenced source cell: {item}" for item in
                      data.get("unreferenced_source_cells", []))
        rows.append((data["record"], issues, path.relative_to(target).as_posix()))
    flagged = [row for row in rows if row[1]]
    unflagged = [row for row in rows if not row[1]]
    sample = sorted(unflagged, key=lambda r: digest({"plan": digest(plan), "record": r[0]}))[
        : max(5, (len(unflagged) + 19) // 20)
    ]
    sampled_paths = {result_path for _, _, result_path in sample}
    entries = []
    for record, issues, result_path in rows:
        file = target / result_path
        entries.append({"record": record, "result_path": result_path,
                        "result_sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                        "issues": issues, "review_flagged": bool(issues),
                        "audit_sample": result_path in sampled_paths})
    index_path = target / "review-index.json.tmp"
    index_path.write_text(json.dumps({"schema_version": "full-run-review-index-v1",
        "plan_sha256": digest(plan), "completed": len(rows), "records": entries},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index_path.replace(target / "review-index.json")
    lines = ["# CSV ingestion review", "", f"Completed: {len(rows)} of {len(plan['records'])}",
             f"Rows with actionable flags: {len(flagged)}", "",
             "All outputs are unreviewed. A row without flags is not an approval.",
             "BASS instrument/control settings require interpretation even if no row-level "
             "issue is listed.", "", "## Rows with flags", ""]
    for record, issues, result_path in flagged:
        lines.append(f"- {record['investigation_id']} / {record['test_id']} "
                     f"([result]({result_path}))")
        lines.extend(f"  - {issue}" for issue in issues)
    lines += ["", "## Suggested audit of rows without flags", "",
              "Deterministic selection; check values and mappings against source.", ""]
    lines.extend(f"- {record['investigation_id']} / {record['test_id']} ([result]({path}))"
                 for record, _, path in sample)
    temporary = target / "review-report.md.tmp"
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(target / "review-report.md")


def execute(
    root: Path,
    plan: dict[str, Any],
    target: Path,
    *,
    allow_calls: bool = False,
    resume: bool = False,
    client: Any = None,
) -> dict[str, Any]:
    requests = rebuild(root, plan)
    summary = {
        "calls_planned": len(requests),
        "model": MODEL,
        "budget_usd": plan["budget_usd"],
        "reservation_usd": plan["reservation_usd"],
        "dry_run": not allow_calls,
    }
    if not allow_calls:
        return summary
    target = target.resolve()
    if not target.is_relative_to((root / "data/processed/full-runs").resolve()):
        raise ValueError("Run directory must be inside data/processed/full-runs")
    if resume:
        if (
            not target.is_dir()
            or json.loads((target / "plan.json").read_text(encoding="utf-8")) != plan
        ):
            raise ValueError("Resume requires the exact saved plan")
    else:
        target.mkdir(parents=True, exist_ok=False)
        (target / "plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    lock = target / ".run-lock"
    lock.mkdir(exist_ok=False)
    try:
        ledger = target / "run-ledger.jsonl"
        events = (
            [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
            if ledger.exists()
            else []
        )
        pending: dict[int, dict[str, Any]] = {}
        completed: dict[int, dict[str, Any]] = {}
        for event in events:
            number = event["number"]
            if not isinstance(number, int) or not 1 <= number <= len(requests):
                raise ValueError("Invalid ledger record")
            if event["status"] == "reserved" and number not in pending and number not in completed:
                if (event.get("record") != requests[number - 1][0] or
                        event.get("reservation_usd") != str(requests[number - 1][3]) or
                        number != len(completed) + 1 or pending):
                    raise ValueError("Ledger reservation does not match planned request")
                pending[number] = event
            elif event["status"] == "complete" and number in pending and number not in completed:
                completed[number] = event
                del pending[number]
            else:
                raise ValueError("Invalid ledger sequence")
        if pending:
            raise ValueError(
                "An earlier request has uncertain status; inspect provider usage and ledger"
            )
        for number, event in completed.items():
            file = target / f"row-{number:04}" / "01.json"
            if (
                not file.is_file()
                or hashlib.sha256(file.read_bytes()).hexdigest() != event["result_sha256"]
            ):
                raise ValueError("A completed response is missing or changed")
        reserved = sum(
            (Decimal(e["reservation_usd"]) for e in events if e["status"] == "reserved"), Decimal(0)
        )
        for number, request in enumerate(requests, 1):
            if number in completed:
                continue
            record, _, _, allowance = request
            if reserved + allowance > Decimal(plan["budget_usd"]):
                raise ValueError("Remaining cumulative reservation would exceed budget")
            append_event(
                ledger,
                {
                    "number": number,
                    "status": "reserved",
                    "reservation_usd": str(allowance),
                    "record": record,
                },
            )
            reserved += allowance
            output = target / f"row-{number:04}"
            run(
                root,
                root / "data/processed/pilot-plan-v1.json",
                output,
                allow_calls=True,
                client=client,
                prepared_requests=[request],
                run_metadata={"plan_sha256": digest(plan)},
            )
            result = output / "01.json"
            append_event(
                ledger,
                {
                    "number": number,
                    "status": "complete",
                    "result_sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
                },
            )
            write_review_report(target, plan)
        summary["completed"] = len(requests)
        return summary
    finally:
        lock.rmdir()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_cmd = commands.add_parser("plan")
    plan_cmd.add_argument("--bass", type=Path, required=True)
    plan_cmd.add_argument("--saffire", type=Path, required=True)
    plan_cmd.add_argument("--budget", type=Decimal, default=Decimal("2.00"))
    plan_cmd.add_argument("--output", type=Path, required=True)
    run_cmd = commands.add_parser("run")
    run_cmd.add_argument("--plan", type=Path, required=True)
    run_cmd.add_argument("--output", type=Path, required=True)
    run_cmd.add_argument("--allow-provider-calls", action="store_true")
    run_cmd.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    if args.command == "plan":
        plan = create_plan(root, {"PSI-25": args.bass, "PSI-99": args.saffire}, args.budget)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(
            json.dumps(
                {
                    "planned": len(plan["records"]),
                    "excluded": len(plan["excluded"]),
                    "reservation_usd": plan["reservation_usd"],
                    "provider_calls": 0,
                }
            )
        )
    else:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        print(
            json.dumps(
                execute(
                    root,
                    plan,
                    args.output,
                    allow_calls=args.allow_provider_calls,
                    resume=args.resume,
                )
            )
        )


if __name__ == "__main__":
    main()
