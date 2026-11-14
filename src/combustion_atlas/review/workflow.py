"""Prepare and apply review decisions without mutating candidate artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from combustion_atlas.artifacts import CandidateBatch
from combustion_atlas.io import read_json, write_json
from combustion_atlas.normalization.schema import ExperimentRecord, ValidationStatus
from combustion_atlas.normalization.validate import validate_candidate

from .models import DecisionFile


def fingerprint_record(record: ExperimentRecord) -> str:
    payload = json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare_decisions(candidate_path: Path, output: Path) -> None:
    batch = CandidateBatch.model_validate(read_json(candidate_path))
    template = {
        "schema_version": batch.schema_version,
        "candidate_file": str(candidate_path),
        "decisions": [
            {
                "investigation_id": record.investigation_id,
                "test_id": record.test_id,
                "candidate_fingerprint": fingerprint_record(record),
                "action": None,
                "reviewer": None,
                "reviewed_at": None,
                "rationale": None,
                "supporting_references": [],
                "corrected_record": None,
            }
            for record in batch.records
        ],
    }
    write_json(output, template)


def apply_decisions(
    candidate_path: Path, decision_path: Path, output: Path, gold_dir: Path | None
) -> None:
    batch = CandidateBatch.model_validate(read_json(candidate_path))
    decisions = DecisionFile.model_validate(read_json(decision_path))
    candidates = {(record.investigation_id, record.test_id): record for record in batch.records}
    accepted: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    exports: list[tuple[Path, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for decision in decisions.decisions:
        if decision.action is None:
            continue
        if decision.action != "correct" and decision.corrected_record is not None:
            raise ValueError("Only correction decisions may include corrected records")
        key = (decision.investigation_id, decision.test_id)
        if key in seen:
            raise ValueError(f"Duplicate decision for {key}")
        seen.add(key)
        if key not in candidates:
            raise ValueError(f"Decision references unknown candidate {key}")
        candidate = candidates[key]
        if fingerprint_record(candidate) != decision.candidate_fingerprint:
            raise ValueError(f"Candidate fingerprint changed for {key}")
        if (
            not decision.reviewer
            or not decision.reviewer.strip()
            or not decision.reviewed_at
            or decision.reviewed_at.utcoffset() is None
            or not decision.rationale
            or not decision.rationale.strip()
            or not decision.supporting_references
            or any(not ref.strip() for ref in decision.supporting_references)
        ):
            raise ValueError(
                f"Completed decision lacks reviewer, timestamp, or rationale for {key}"
            )
        selected: ExperimentRecord | None = None
        if decision.action == "accept":
            if candidate.validation_status == ValidationStatus.REJECTED:
                raise ValueError(f"Rejected candidate cannot be accepted: {key}")
            selected = candidate
        elif decision.action == "correct":
            if decision.corrected_record is None:
                raise ValueError(f"Correct decision requires corrected_record for {key}")
            selected = ExperimentRecord.model_validate(decision.corrected_record)
            if (selected.investigation_id, selected.test_id) != key:
                raise ValueError(f"Correction cannot change run identity for {key}")
            if (
                selected.sample_id != candidate.sample_id
                or selected.raw_cells != candidate.raw_cells
                or selected.provenance != candidate.provenance
            ):
                raise ValueError(f"Correction cannot change source evidence for {key}")
            measurements = list(selected.conditions.dimensions.values()) + list(
                selected.conditions.measurements.values()
            )
            measurements += [
                m
                for m in (
                    selected.conditions.oxygen_pct,
                    selected.conditions.pressure_kpa,
                    selected.conditions.airflow_cm_s,
                    selected.conditions.temperature,
                )
                if m
            ]
            measurements += list(selected.outcomes)
            source = candidate.provenance[0]
            for m in measurements:
                p = m.provenance
                if (
                    p.source_sha256 != source.source_sha256
                    or p.source_url != source.source_url
                    or p.record_number != source.record_number
                    or p.column_name not in candidate.raw_cells
                    or m.original_value != candidate.raw_cells[p.column_name]
                ):
                    raise ValueError(f"Correction has unsupported source provenance for {key}")
            selected = validate_candidate(selected)
        if selected is not None:
            item = selected.model_dump(mode="json")
            accepted.append(item)
            if gold_dir is not None:
                if any(char in selected.investigation_id + selected.test_id for char in "/\\"):
                    raise ValueError("Record identity cannot contain path separators")
                exports.append(
                    (gold_dir / f"{selected.investigation_id}-{selected.test_id}.json", item)
                )
        audit.append(decision.model_dump(mode="json"))
    payload = {
        "schema_version": batch.schema_version,
        "candidate_file": str(candidate_path),
        "decision_file": str(decision_path),
        "accepted_records": accepted,
        "audit": audit,
    }
    destinations = [output, *(path for path, _ in exports)]
    if len({p.resolve() for p in destinations}) != len(destinations):
        raise ValueError("Review output paths must be distinct")
    if any(p.exists() for p in destinations):
        raise ValueError("Choose new output paths; review artifacts are immutable")
    if any(
        p.resolve() in {candidate_path.resolve(), decision_path.resolve()} for p in destinations
    ):
        raise ValueError("Outputs cannot replace review inputs")
    for path, item in exports:
        write_json(path, item)
    write_json(output, payload)
