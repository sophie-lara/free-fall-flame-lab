"""Prepare and apply review decisions without mutating candidate artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from combustion_atlas.artifacts import CandidateBatch
from combustion_atlas.io import read_json, write_json
from combustion_atlas.normalization.schema import ExperimentRecord, ValidationStatus

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
    for decision in decisions.decisions:
        if decision.action is None:
            continue
        key = (decision.investigation_id, decision.test_id)
        if key not in candidates:
            raise ValueError(f"Decision references unknown candidate {key}")
        candidate = candidates[key]
        if fingerprint_record(candidate) != decision.candidate_fingerprint:
            raise ValueError(f"Candidate fingerprint changed for {key}")
        if not decision.reviewer or not decision.reviewed_at or not decision.rationale:
            raise ValueError(
                f"Completed decision lacks reviewer, timestamp, or rationale for {key}"
            )
        selected: ExperimentRecord | None = None
        if decision.action == "accept":
            selected = candidate.model_copy(
                update={"validation_status": ValidationStatus.VALIDATED}
            )
        elif decision.action == "correct":
            if decision.corrected_record is None:
                raise ValueError(f"Correct decision requires corrected_record for {key}")
            selected = ExperimentRecord.model_validate(decision.corrected_record)
            if (selected.investigation_id, selected.test_id) != key:
                raise ValueError(f"Correction cannot change run identity for {key}")
            selected = selected.model_copy(update={"validation_status": ValidationStatus.VALIDATED})
        if selected is not None:
            item = selected.model_dump(mode="json")
            accepted.append(item)
            if gold_dir is not None:
                write_json(gold_dir / f"{selected.investigation_id}-{selected.test_id}.json", item)
        audit.append(decision.model_dump(mode="json"))
    write_json(
        output,
        {
            "schema_version": batch.schema_version,
            "candidate_file": str(candidate_path),
            "decision_file": str(decision_path),
            "accepted_records": accepted,
            "audit": audit,
        },
    )
