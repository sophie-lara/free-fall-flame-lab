"""Promote reviewed FLEX table results into a reviewed-evidence/decisions pair.

Inputs are bound by hash: the combined planned-test candidates (Tables 6-12) and the
extractions of the background tables (2, 14) named in the FLEX review record. Planned
tests become ``planned_test_condition`` records (cards, never coverage runs). Background
tables become one ``background_table_row`` record per data row, with every cell kept
verbatim as an additional field and reviewer-supplied symbol definitions attached as
``definition`` notes. All notes and caveats from mapping and review are kept.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from combustion_atlas.ingestion.flex_pdf_run import SOURCE, TableExtraction

from .evidence_schema import EvidenceCandidate
from .fixtures import ReviewedEvidence, fingerprint

UNRESOLVED = {"ambiguous", "unresolved", "pending"}
BACKGROUND_TABLES = ("2", "14")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _symbol(header: str) -> str:
    """Leading symbol of a header: 'D_IO (cm²/s)' -> 'D_IO', 'Le_O (D_O)' -> 'Le_O'."""
    return re.split(r"\s|\(", header.strip(), maxsplit=1)[0]


def background_candidates(
    extraction: TableExtraction, label: str, definitions: dict[str, str], basis: str
) -> list[dict[str, Any]]:
    headers = {c.column: c.text or "" for c in extraction.cells if c.role == "header"}
    rows: dict[int, dict[int, Any]] = {}
    for c in extraction.cells:
        if c.role == "data":
            rows.setdefault(c.row, {})[c.column] = c
    out = []
    for row, cells in sorted(rows.items()):
        name = (cells[min(cells)].text or f"row{row}").strip()
        fields: dict[str, Any] = {}
        for column, cell in sorted(cells.items()):
            header = headers.get(column, f"column {column}")
            value: dict[str, Any] = {
                "original_value": cell.text,
                "original_unit": None,
                "provenance": {
                    "source_url": SOURCE["source_url"],
                    "file": Path(SOURCE["path"]).name,
                    "row": cell.row + 1,
                    "column": header,
                    "page": cell.page,
                    "table": label,
                    "synthetic": False,
                    "source_sha256": SOURCE["sha256"],
                },
                "value": cell.text,
                "unit": None,
                "qualifier": None,
                "uncertainty": None,
                "notes": [],
            }
            meaning = definitions.get(_symbol(header))
            if meaning:
                value["notes"].append(
                    {
                        "kind": "definition",
                        "text": f"{_symbol(header)}: {meaning} ({basis})",
                        "by": "reviewer",
                        "decision": None,
                    }
                )
            fields[header] = value
        candidate = {
            "identity": {
                "investigation_id": SOURCE["investigation_id"],
                "test_id": f"FLEX-T{label}-{re.sub(r'[^A-Za-z0-9]+', '', name) or row}",
                "sample_id": None,
            },
            "conditions": {},
            "outcomes": [],
            "instrument_settings": {},
            "extra_metadata": {},
            "additional_fields": fields,
            "raw_cells": [
                {k: v[k] for k in ("original_value", "original_unit", "provenance")}
                for v in fields.values()
            ],
            "extraction_confidence": None,
            "validation_status": "review_required",
            "human_review_status": "unreviewed",
            "issues": [
                {
                    "code": "evidence_class",
                    "field": "Record",
                    "message": f"Background data row from EIRD Table {label} "
                    f"({extraction.caption}); literature or calculated values, not a FLEX run.",
                    "severity": "review",
                }
            ],
        }
        EvidenceCandidate.model_validate(candidate)
        out.append(candidate)
    return out


def promote(root: Path, review_path: Path, matrix_path: Path) -> list[ReviewedEvidence]:
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("schema_version") != "flex-table-review-v1":
        raise ValueError("Not a FLEX table review record")
    promotion = review.get("promotion") or {}
    if not promotion.get("decided_by") or not promotion.get("decided_at"):
        raise ValueError("Review record has no promotion decision")
    tables = review["tables"]
    reviewer, when = promotion["decided_by"], promotion["decided_at"]

    planned: list[tuple[dict[str, Any], str, list[str]]] = []
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    for item in matrix["inputs"]:
        if _sha(root / item["candidates"]) != item["sha256"]:
            raise ValueError(f"Candidate file changed: {item['candidates']}")
        if tables.get(item["table"], {}).get("status") not in {"checked", "spot_checked"}:
            raise ValueError(f"Table {item['table']} has no recorded extraction check")
    labels = {
        r["identity"]["test_id"]: r["identity"]["test_id"].split("-")[1][1:]
        for r in matrix["records"]
    }
    for record in matrix["records"]:
        planned.append((record, labels[record["identity"]["test_id"]], []))

    background: list[tuple[dict[str, Any], str, list[str]]] = []
    for label in BACKGROUND_TABLES:
        entry = tables.get(label, {})
        if entry.get("status") != "checked":
            raise ValueError(f"Background Table {label} is not checked")
        path = root / entry["extraction"]
        if _sha(path) != entry["extraction_sha256"]:
            raise ValueError(f"Extraction changed: {entry['extraction']}")
        result = json.loads(path.read_text(encoding="utf-8"))
        extraction = TableExtraction.model_validate(result["extraction"])
        definitions = entry.get("symbol_definitions", {})
        basis = entry.get("definition_source", "reviewer-supplied")
        questions: list[str] = []
        for candidate in background_candidates(extraction, label, definitions, basis):
            background.append((candidate, label, questions))

    out = []
    for original, label, questions in [*planned, *background]:
        reviewed = copy.deepcopy(original)
        notes = [
            n
            for v in [
                *reviewed["conditions"].values(),
                *reviewed["outcomes"],
                *reviewed.get("additional_fields", {}).values(),
            ]
            for n in v.get("notes", [])
        ]
        reviewed["human_review_status"] = "accepted"
        reviewed["validation_status"] = (
            "review_required" if any(n["kind"] in UNRESOLVED for n in notes) else "validated"
        )
        reviewed["issues"] = [
            i for i in reviewed["issues"] if i["code"] != "human_review_required"
        ] + [
            {
                "code": "review_decisions",
                "field": "Record",
                "message": f"Accepted by {reviewer} ({when[:10]}) with the FLEX table review "
                "record (docs/review_decisions/flex-eird-tables-v1-review.md); notes on "
                "each value record ambiguities and definitions.",
                "severity": "review",
            }
        ]
        EvidenceCandidate.model_validate(reviewed)
        check = tables[label]["status"]
        open_questions = [f"{n['text']}" for n in notes if n["kind"] in UNRESOLVED]
        if check == "spot_checked":
            open_questions.append("Table transcription was spot-checked, not line by line.")
        source = reviewed["raw_cells"][0]["provenance"]
        reference = (
            f"{source['file']} PDF page {source['page']}, Table {label}, row {source['row']} ; "
            f"{source['source_url']}"
        )
        out.append(
            ReviewedEvidence(
                investigation_id=reviewed["identity"]["investigation_id"],
                test_id=reviewed["identity"]["test_id"],
                evidence_kind="background_table_row"
                if label in BACKGROUND_TABLES
                else "planned_test_condition",
                source_sha256=SOURCE["sha256"],
                candidate_fingerprint=fingerprint(original),
                review_action="accept_extraction",
                supporting_references=[reference],
                confirming_note={
                    "investigation_id": reviewed["identity"]["investigation_id"],
                    "test_id": reviewed["identity"]["test_id"],
                    "reviewer": reviewer,
                    "decision": "accept_extraction",
                    "note": promotion["decision"],
                    "quote": promotion.get("quote"),
                    "saved_at_utc": when,
                    "extraction_check": check,
                    "review_record_sha256": _sha(review_path),
                    "candidate_fingerprint": fingerprint(original),
                },
                review_history=[],
                original_candidate=original,
                reviewed_candidate=reviewed,
                transformations=[],
                unresolved_questions=list(dict.fromkeys([*questions, *open_questions])),
            )
        )
    ids = [(r.investigation_id, r.test_id) for r in out]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate identities in FLEX reviewed evidence")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--review", type=Path, default=Path("docs/review_decisions/flex-eird-tables-v1-review.json")
    )
    parser.add_argument(
        "--matrix", type=Path, default=Path("data/processed/flex-matrix-candidates-v1.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/reviewed-evidence-flex-v1.json")
    )
    parser.add_argument(
        "--decisions-output",
        type=Path,
        default=Path("data/processed/reviewed-decisions-flex-v1.json"),
    )
    args = parser.parse_args()
    root = args.workspace.resolve()
    records = promote(root, root / args.review, root / args.matrix)
    payload = {
        "schema_version": "reviewed-evidence-v1",
        "scope": "FLEX EIRD table results promoted to reviewed status; notes, definitions and "
        "open questions retained",
        "records": [r.model_dump(mode="json") for r in records],
    }
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    decisions = {
        "schema_version": "reviewed-decisions-v1",
        "fixture_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "decisions": [
            {
                "investigation_id": r.investigation_id,
                "test_id": r.test_id,
                "candidate_fingerprint": r.candidate_fingerprint,
                "source_sha256": r.source_sha256,
                "reviewed_fingerprint": fingerprint(r.reviewed_candidate),
                "action": "accept",
                "reviewer": r.confirming_note["reviewer"],
                "reviewed_at": r.confirming_note["saved_at_utc"],
                "rationale": r.confirming_note["note"],
                "extraction_check": r.confirming_note["extraction_check"],
                "supporting_references": r.supporting_references,
                "unresolved_questions": r.unresolved_questions,
            }
            for r in records
        ],
    }
    decision_text = json.dumps(decisions, indent=2, ensure_ascii=False) + "\n"
    for path, text in ((args.output, content), (args.decisions_output, decision_text)):
        target = root / path
        if target.exists() and target.read_text(encoding="utf-8") != text:
            parser.error(f"Choose a new output path; existing artifact differs: {path}")
    for path, text in ((args.output, content), (args.decisions_output, decision_text)):
        (root / path).write_bytes(text.encode("utf-8"))
    kinds: dict[str, int] = {}
    for r in records:
        kinds[r.evidence_kind] = kinds.get(r.evidence_kind, 0) + 1
    print(json.dumps({"records": len(records), "by_kind": kinds}))


if __name__ == "__main__":
    main()
