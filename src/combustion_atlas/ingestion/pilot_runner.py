"""Run the source-bound pilot with a conservative local spending reservation."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

from combustion_atlas.ingestion.models import RawRow
from combustion_atlas.normalization.extractor import extract_bass_row
from combustion_atlas.review.fixtures import fingerprint

from .llm_handoff import (
    Proposal,
    SourceBatch,
    SourceCellRef,
    check_proposal,
    csv_batch,
    review_markdown,
)
from .llm_transcribe import INSTRUCTIONS, PROMPT_VERSION, request_payload
from .pilot_mapping import coverage_issues, flex_mapping, reviewed_source_issues
from .pilot_plan import SELECTION

MODEL = "gpt-6-luna"
BUDGET = Decimal("2.00")
MAX_OUTPUT = 2500
MAX_CALLS = 11
# Conservative assumed rates per million tokens, above standard short-context prices.
INPUT_RATE = Decimal("0.20")
OUTPUT_RATE = Decimal("1.00")


def source_batch(
    root: Path, record: dict[str, Any], flex_records: list[dict[str, Any]]
) -> SourceBatch:
    path = (root / record["source_file"]).resolve()
    if not path.is_relative_to((root / "data/raw").resolve()):
        raise ValueError("Source outside data/raw")
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["source_sha256"]:
        raise ValueError("Source checksum mismatch")
    if path.suffix.lower() == ".csv":
        return csv_batch(path, record["row"])
    if path.suffix.lower() != ".pdf" or record["investigation_id"] != "PSI-69":
        raise ValueError("Unsupported source")
    matches = [
        x
        for x in flex_records
        if x["investigation_id"] == record["investigation_id"] and x["test_id"] == record["test_id"]
    ]
    if len(matches) != 1:
        raise ValueError("Missing or duplicate FLEX source transcription")
    raw = matches[0]["original_candidate"]["raw_cells"]
    if fingerprint(matches[0]["original_candidate"]) != matches[0]["candidate_fingerprint"]:
        raise ValueError("FLEX captured candidate fingerprint mismatch")
    if any(
        c["provenance"]["source_sha256"] != record["source_sha256"]
        or c["provenance"]["row"] != record["row"]
        or c["provenance"]["page"] != record["page"]
        or c["provenance"]["table"] != record["table"]
        for c in raw
    ):
        raise ValueError("FLEX transcription source mismatch")
    cells = []
    for i, cell in enumerate(raw):
        loc = cell["provenance"]
        value = cell["original_value"]
        state: Literal["unreadable", "blank", "present"] = (
            "unreadable" if value is None else "blank" if value == "" else "present"
        )
        cells.append(
            SourceCellRef(
                source_sha256=record["source_sha256"],
                filename=path.name,
                source_url=loc["source_url"],
                kind="pdf_table",
                artifact_id="FLEX-table-13-capture",
                physical_page=record["page"],
                table_row=record["row"] - 1,
                table_column=i,
                text=value,
                state=state,
                unit=cell.get("original_unit"),
                source_label=loc["column"],
            )
        )
    pdf = PdfReader(path)
    page = record["page"]
    if page <= 1 or page >= len(pdf.pages):
        raise ValueError("FLEX context pages outside source")
    context = ["FLEX table cells are a previously captured transcription, not PDF vision."]
    context.extend(
        f"Physical page {p}:\n{pdf.pages[p - 1].extract_text() or ''}"
        for p in (page - 1, page, page + 1)
    )
    return SourceBatch(cells=cells, context=context)


def reserve(payload: str) -> Decimal:
    # Reserve at least one token per UTF-8 byte, including schema and ample framing.
    schema = json.dumps(Proposal.model_json_schema(), ensure_ascii=False)
    input_upper = len((payload + INSTRUCTIONS + schema).encode("utf-8")) + 16384
    return (Decimal(input_upper) * INPUT_RATE + Decimal(MAX_OUTPUT) * OUTPUT_RATE) / 1_000_000


def deterministic_bass_fields(batch: SourceBatch, investigation_id: str) -> dict[str, Any]:
    """Extract source-supported material details independently of the model proposal."""
    if investigation_id != "PSI-25" or any(c.kind != "csv" for c in batch.cells):
        return {}
    row_number = batch.cells[0].csv_record
    if row_number is None or any(
        c.csv_record != row_number or c.csv_column is None for c in batch.cells
    ):
        raise ValueError("BASS source cells must belong to one CSV row")
    row = RawRow(record_number=row_number, cells={str(c.csv_column): c.text for c in batch.cells})
    record = extract_bass_row(
        row,
        investigation_id=investigation_id,
        source_url="https://psi.nasa.gov/physci/repo/data/investigations/PSI-25",
        source_sha256=batch.cells[0].source_sha256,
    )
    return {
        "material": record.conditions.material,
        "geometry": record.conditions.geometry,
        "dimensions": {
            name: value.model_dump(mode="json")
            for name, value in record.conditions.dimensions.items()
        },
    }


def identity_issue(record: dict[str, Any], proposal: Proposal) -> str | None:
    """Accept only documented pilot aliases; distinguish unknown labels from conflicts."""

    def normalize(value: str) -> str:
        return " ".join(value.casefold().strip().split())

    investigation_aliases = {
        "psi-25": "PSI-25",
        "bass-ii": "PSI-25",
        "psi-25 bass-ii": "PSI-25",
        "psi-69": "PSI-69",
        "psi-99": "PSI-99",
        "saffire-2": "PSI-99",
    }
    test_aliases = {
        "table 13, ar row (background-study result; not an individual flight run)": "FLEX-T13-Ar",
        "flex background study, table 13, n2 row": "FLEX-T13-N2",
        "flex-table-13-he-row": "FLEX-T13-He",
    }
    for investigation, tests in SELECTION.items():
        investigation_aliases[normalize(investigation)] = investigation
        for test in tests:
            test_aliases[normalize(test)] = test
            if investigation == "PSI-99":
                test_aliases[normalize(test.removeprefix("SAFFIRE-II-"))] = test
    mapped_investigation = investigation_aliases.get(normalize(proposal.investigation_id))
    mapped_test = test_aliases.get(normalize(proposal.test_id))
    if (mapped_investigation and mapped_investigation != record["investigation_id"]) or (
        mapped_test and mapped_test != record["test_id"]
    ):
        return "identity_mismatch"
    if mapped_investigation is None or mapped_test is None:
        return "identity_unresolved"
    return None


def build(root: Path, plan_path: Path) -> list[tuple[dict[str, Any], SourceBatch, str, Decimal]]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["model"] != MODEL or Decimal(str(plan["budget_usd"])) != BUDGET:
        raise ValueError("Unexpected model or pilot budget")
    records = plan["records"]
    if not records or len(records) > MAX_CALLS:
        raise ValueError("Pilot call limit exceeded")
    if len({(r["investigation_id"], r["test_id"]) for r in records}) != len(records):
        raise ValueError("Duplicate pilot identity")
    actual = {(r["investigation_id"], r["test_id"]): r["split"] for r in records}
    expected = {
        (investigation, test): split
        for investigation, tests in SELECTION.items()
        for test, split in tests.items()
    }
    if actual != expected:
        raise ValueError("Pilot selection or holdout split changed")
    evidence = json.loads(
        (root / "data/processed/reviewed-evidence-v1.json").read_text(encoding="utf-8")
    )["records"]
    requests = []
    for record in records:
        batch = source_batch(root, record, evidence)
        payload = request_payload(batch)
        requests.append((record, batch, payload, reserve(payload)))
    if sum((r[3] for r in requests), Decimal(0)) > BUDGET:
        raise ValueError("Conservative reservation exceeds budget")
    return requests


def run(
    root: Path, plan: Path, output: Path, *, allow_calls: bool = False, client: Any = None
) -> dict[str, Any]:
    requests = build(root, plan)
    summary: dict[str, Any] = {
        "model": MODEL,
        "calls": len(requests),
        "reservation_usd": str(sum((r[3] for r in requests), Decimal(0))),
        "budget_usd": str(BUDGET),
        "dry_run": not allow_calls,
    }
    if not allow_calls:
        return summary
    load_dotenv(root / ".env", override=False)
    # New directory prevents automatic retries after interrupted or uncertain requests.
    output.mkdir(parents=True, exist_ok=False)
    api = client or OpenAI(timeout=60.0, max_retries=0)
    ledger = output / "ledger.jsonl"
    for number, (record, batch, payload, reservation) in enumerate(requests, 1):
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {"request": number, "status": "reserved", "reserved_usd": str(reservation)}
                )
                + "\n"
            )
        response = api.responses.parse(
            model=MODEL,
            store=False,
            max_output_tokens=MAX_OUTPUT,
            instructions=INSTRUCTIONS,
            input=payload,
            text_format=Proposal,
        )
        proposal = response.output_parsed
        if not isinstance(proposal, Proposal) or response.usage is None:
            raise ValueError("Incomplete response or missing usage; stop and inspect ledger")
        issues = check_proposal(batch, proposal)
        deterministic_fields = deterministic_bass_fields(batch, record["investigation_id"])
        canonical_fields, mapping_issues = flex_mapping(batch, record)
        issues.extend(mapping_issues)
        issues.extend(reviewed_source_issues(batch, record))
        issues.extend(coverage_issues(batch, proposal, record))
        identity_status = identity_issue(record, proposal)
        if identity_status:
            from .llm_handoff import ReviewIssue

            issues.append(
                ReviewIssue(
                    field="identity",
                    code=identity_status,
                    message=(
                        "Model identity conflicts with or cannot be matched to the selected row."
                    ),
                )
            )
        result = {
            "record": record,
            "status": "unreviewed",
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": hashlib.sha256(INSTRUCTIONS.encode()).hexdigest(),
            "response_id": response.id,
            "model_returned": response.model,
            "usage": response.usage.model_dump(mode="json"),
            "source": batch.model_dump(mode="json"),
            "proposal": proposal.model_dump(mode="json"),
            "deterministic_material_fields": deterministic_fields,
            "source_mappings": canonical_fields,
            "issues": [issue.model_dump(mode="json") for issue in issues],
        }
        (output / f"{number:02}.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (output / f"{number:02}.review.md").write_text(
            review_markdown(proposal, issues), encoding="utf-8"
        )
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"request": number, "status": "complete", "usage": result["usage"]})
                + "\n"
            )
        usage = response.usage
        actual_cost = (
            Decimal(usage.input_tokens) * INPUT_RATE + Decimal(usage.output_tokens) * OUTPUT_RATE
        ) / 1_000_000
        if actual_cost > reservation:
            raise ValueError("Actual token usage exceeds reservation; stop and inspect ledger")
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
