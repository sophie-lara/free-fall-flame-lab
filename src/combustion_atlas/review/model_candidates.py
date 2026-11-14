"""Expose source-bound model proposals for manual review, never approval."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from combustion_atlas.app.server import Workspace
from combustion_atlas.ingestion.llm_handoff import SourceBatch
from combustion_atlas.ingestion.mapping_contract import MappedRow, validate_mapping
from combustion_atlas.ingestion.table_parser import read_csv_losslessly

from .evidence_schema import EvidenceCandidate

OUTCOMES = {"final_oxygen", "final_co2", "final_co", "burn_time",
            "burn_length_unspecified_gravity", "spread_length_unspecified_gravity",
            "burn_length_1g", "spread_rate_1g"}
INSTRUMENTS = {"flow_restrictor", "fan_display", "air_display", "radiometer_gain", "frames_shot",
               "camera_1", "camera_2"}
IDENTIFIERS = {"principal_investigator", "test_id", "sample_id", "date", "gmt"}


def convert(root: Path, path: Path) -> dict[str, Any]:
    raw_result = path.read_bytes()
    result = json.loads(raw_result)
    record = result["record"]
    investigation = record["investigation_id"]
    if investigation not in {"PSI-25", "PSI-99"} or result["status"] != "unreviewed":
        raise ValueError("Only unreviewed BASS or Saffire CSV model results are supported")
    source_path = (root / record["source_file"]).resolve()
    if not source_path.is_relative_to((root / "data/raw").resolve()):
        raise ValueError("Source is outside data/raw")
    table = read_csv_losslessly(source_path)
    if table.sha256 != record["source_sha256"]:
        raise ValueError("Source hash has changed")
    rows = [row for row in table.rows if row.record_number == record["record_number"]]
    if len(rows) != 1:
        raise ValueError("Source row identity mismatch")
    source_id = (rows[0].cells.get("Test #" if investigation == "PSI-25" else "Sample Number")
                 or "").strip()
    expected_id = source_id if investigation == "PSI-25" else f"SAFFIRE-II-{source_id}"
    if expected_id != record["test_id"]:
        raise ValueError("Source row identity mismatch")
    batch = SourceBatch.model_validate(result["source"])
    if len(batch.cells) != len(rows[0].cells):
        raise ValueError("Source cell count mismatch")
    for source, (column, text) in zip(batch.cells, rows[0].cells.items(), strict=True):
        if (source.kind != "csv" or source.csv_record != rows[0].record_number or
            source.csv_column != column or source.text != text or
            source.source_sha256 != table.sha256):
            raise ValueError("Source cell mismatch")
    proposal = MappedRow.model_validate(result["proposal"])
    profile = "bass_ii" if investigation == "PSI-25" else "saffire_ii"
    if proposal.profile != profile:
        raise ValueError("Unexpected mapping profile")
    url = f"https://psi.nasa.gov/physci/repo/data/investigations/{investigation}"
    def cell_at(index: int) -> dict[str, Any]:
        c = batch.cells[index]
        return {"original_value": c.text, "original_unit": c.unit, "provenance": {
            "source_url": url, "file": source_path.name, "row": c.csv_record,
            "column": c.csv_column, "page": None, "table": None, "synthetic": False,
            "source_sha256": table.sha256}}

    conditions: dict[str, Any] = {}
    outcomes = []
    instruments: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    issues: list[dict[str, str]] = []
    if investigation == "PSI-99":
        for source_row in table.rows:
            note = source_row.cells.get("Sample Number") or ""
            match = re.match(r"^\s*Note\s+(\d+)\b", note, re.I)
            if not match:
                continue
            metadata[f"source_note_{match.group(1)}"] = {
                "original_value": note, "original_unit": None,
                "provenance": {"source_url": url, "file": source_path.name,
                    "row": source_row.record_number, "column": "Sample Number", "page": None,
                    "table": None, "synthetic": False, "source_sha256": table.sha256}}
        if metadata:
            issues.append({"code": "source_notes", "field": "Source notes",
                "message": "Source includes numbered notes; inspect their relevance in the CSV. "
                           "Notes are preserved in candidate metadata.", "severity": "review"})
    checks = list(dict.fromkeys([*result.get("validation_issues", []),
                                 *validate_mapping(proposal, profile, batch)]))
    for check in checks:
        issues.append({"code": "mapping_validation", "field": "Mapping", "message": check,
                       "severity": "review"})
    for unlinked in result.get("unreferenced_source_cells", []):
        issues.append({"code": "unreferenced_source_cell", "field": "Source",
                       "message": f"Unreferenced source cell: {unlinked}", "severity": "review"})
    for source_issue in result.get("source_issues", []):
        issues.append({"code": source_issue["code"], "field": source_issue["field"],
                       "message": source_issue["message"], "severity": "review"})
    seen: set[str] = set()
    for field in proposal.fields:
        if not field.source_indexes or any(i < 0 or i >= len(batch.cells)
                                           for i in field.source_indexes):
            raise ValueError("Invalid model field source reference")
        if field.canonical_field != "unmapped" and field.canonical_field in seen:
            raise ValueError("Duplicate model field requires manual resolution")
        seen.add(field.canonical_field)
        primary = cell_at(field.source_indexes[0])
        if len(field.source_indexes) != 1:
            issues.append({"code": "multiple_source_cells", "field": field.canonical_field,
                           "message": "Consult model output for all source cells "
                                      f"{field.source_indexes}.",
                           "severity": "review"})
        if field.note:
            issues.append({"code": "model_note", "field": field.canonical_field,
                           "message": field.note, "severity": "review"})
        if field.canonical_field in INSTRUMENTS:
            instruments[field.canonical_field] = primary
        elif field.canonical_field in IDENTIFIERS or field.canonical_field == "unmapped":
            name = (f"unmapped_{len(metadata)}" if field.canonical_field == "unmapped"
                    else field.canonical_field)
            metadata[name] = primary
        else:
            value = {**primary, "value": field.value, "unit": field.unit,
                     "qualifier": field.qualifier or (field.missingness if field.missingness !=
                     "reported" else None), "uncertainty": field.note}
            if field.canonical_field in OUTCOMES:
                outcomes.append({**value, "outcome_type": field.canonical_field})
            elif field.canonical_field in conditions:
                raise ValueError("Duplicate model condition requires manual resolution")
            else:
                conditions[field.canonical_field] = value
    # Supply only deterministic geometry that is clearly present in the same source cell.
    material = result.get("deterministic_material_fields", {})
    if "geometry" not in conditions and material.get("geometry") == "film":
        matches = [i for i, c in enumerate(batch.cells) if c.csv_column == "Fuel Sample Material"]
        if len(matches) == 1 and re.search(r"\bfilm\b", batch.cells[matches[0]].text or "", re.I):
            conditions["geometry"] = {**cell_at(matches[0]), "value": "film", "unit": None,
                                      "qualifier": None, "uncertainty": "Deterministic extraction"}
    issues.append({"code": "human_review_required", "field": "Record",
                   "message": "Unreviewed model proposal; verify against source before approval.",
                   "severity": "review"})
    candidate = EvidenceCandidate.model_validate({"identity": {"investigation_id": investigation,
        "test_id": record["test_id"], "sample_id": rows[0].cells.get(
            "Sample #" if investigation == "PSI-25" else "Sample Number")},
        "conditions": conditions, "outcomes": outcomes, "instrument_settings": instruments,
        "extra_metadata": metadata, "raw_cells": [cell_at(i) for i in range(len(batch.cells))],
        "extraction_confidence": None, "validation_status": "review_required",
        "human_review_status": "unreviewed", "issues": issues})
    return {"candidate": candidate.model_dump(mode="json"), "result_file": path.name,
            "result_sha256": hashlib.sha256(raw_result).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-index", type=Path,
                        help="Import only flagged rows and the audit sample from a full run")
    args = parser.parse_args()
    root = args.workspace.resolve()
    if args.review_index:
        result_root = args.results.resolve()
        if args.review_index.resolve().parent != result_root:
            raise ValueError("Review index must be inside the results directory")
        index = json.loads(args.review_index.read_text(encoding="utf-8"))
        if index.get("schema_version") != "full-run-review-index-v1":
            raise ValueError("Unsupported review index")
        plan = json.loads((result_root / "plan.json").read_text(encoding="utf-8"))
        plan_hash = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False,
            separators=(",", ":")).encode()).hexdigest()
        if (index.get("plan_sha256") != plan_hash or
                index.get("completed") != len(plan["records"]) or
                len(index["records"]) != len(plan["records"])):
            raise ValueError("Review index is incomplete or does not match the run plan")
        paths = []
        for entry in index["records"]:
            if not (entry["review_flagged"] or entry["audit_sample"]):
                continue
            path = (result_root / entry["result_path"]).resolve()
            if (not path.is_relative_to(result_root) or not path.is_file() or
                    hashlib.sha256(path.read_bytes()).hexdigest() != entry["result_sha256"]):
                raise ValueError("Review index result is missing or changed")
            paths.append(path)
        if len(set(paths)) != len(paths):
            raise ValueError("Duplicate results in review index")
        args.results = result_root
    else:
        paths = sorted(args.results.glob("[0-9][0-9].json"))
        paths += sorted(args.results.glob("row-*/01.json"))
    if not paths:
        raise ValueError("No result files")
    adapted = [convert(root, path) for path in paths]
    for item, path in zip(adapted, paths, strict=True):
        item["result_file"] = path.relative_to(args.results).as_posix()
    keys = [(item["candidate"]["identity"]["investigation_id"],
             item["candidate"]["identity"]["test_id"]) for item in adapted]
    workspace = Workspace(root)
    existing = {(r.investigation_id, r.test_id) for r in workspace.records()} | {
        (r["identity"]["investigation_id"], r["identity"]["test_id"])
        for r in workspace.preserved()}
    if len(set(keys)) != len(keys) or set(keys) & existing:
        raise ValueError("Candidate identity already exists in the review workspace")
    output_root = (root / "data/review/model-candidates").resolve()
    target = args.output.resolve()
    if not target.is_relative_to(output_root) or target.suffix != ".json":
        raise ValueError("Place candidate JSON under data/review/model-candidates")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump({"records": [item["candidate"] for item in adapted], "model_results": [
            {"file": item["result_file"], "sha256": item["result_sha256"]} for item in adapted]},
            stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Prepared {len(adapted)} unreviewed candidates")


if __name__ == "__main__":
    main()
