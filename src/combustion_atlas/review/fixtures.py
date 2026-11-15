"""Build traceable reviewed evidence fixtures from confirmed review records."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidence_schema import EvidenceCandidate


class ReviewedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    investigation_id: str
    test_id: str
    evidence_kind: Literal["run", "background_table_row", "planned_test_condition"]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_action: Literal["accept_extraction", "correction_proposed", "needs_research"]
    supporting_references: list[str] = Field(min_length=1)
    confirming_note: dict[str, Any]
    review_history: list[dict[str, Any]]
    original_candidate: dict[str, Any]
    reviewed_candidate: dict[str, Any]
    transformations: list[str]
    unresolved_questions: list[str]


def fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def prepare(root: Path) -> list[ReviewedEvidence]:
    review = root / "data/review"
    archive = review / "preserved-review"
    reconciliation_path = review / "reconciled-review.json"
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    notes: list[dict[str, Any]] = []
    for note_file in (archive / "human-notes.jsonl", review / "human-notes.jsonl"):
        if note_file.is_file():
            with note_file.open(encoding="utf-8") as stream:
                notes.extend(json.loads(line) for line in stream if line.strip())
    paths = [
        archive / "psi-25-b1-b5.json",
        archive / "additional-candidates/flex-table13.json",
        archive / "additional-candidates/saffire-ii.json",
    ]
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        for record in json.loads(path.read_text(encoding="utf-8"))["records"]:
            key = (record["identity"]["investigation_id"], record["identity"]["test_id"])
            if key in candidates:
                raise ValueError(f"Duplicate candidate identity: {key}")
            candidates[key] = record
    fixtures = []
    seen = set()
    for entry in reconciliation["entries"]:
        key = (entry["investigation_id"], entry["test_id"])
        if key in seen or key not in candidates:
            raise ValueError(f"Duplicate or unknown reviewed record: {key}")
        seen.add(key)
        record = candidates[key]
        EvidenceCandidate.model_validate(record)
        if fingerprint(record) != entry["candidate_fingerprint"]:
            raise ValueError(f"Candidate fingerprint mismatch: {key}")
        note = entry["latest_confirming_note"]
        if (
            note.get("candidate_fingerprint") != entry["candidate_fingerprint"]
            or note.get("investigation_id") != key[0]
            or note.get("test_id") != key[1]
            or note.get("decision") != entry["proposed_action"]
        ):
            raise ValueError(f"Missing candidate-bound confirmation: {key}")
        if not str(note.get("reviewer", "")).strip() or not str(note.get("note", "")).strip():
            raise ValueError(f"Confirmation lacks reviewer or rationale: {key}")
        timestamp = datetime.fromisoformat(note["saved_at_utc"].replace("Z", "+00:00"))
        if timestamp.utcoffset() is None:
            raise ValueError(f"Confirmation requires a timezone: {key}")
        persisted_note = {k: v for k, v in note.items() if k != "binding_status"}
        if persisted_note not in notes:
            raise ValueError(f"Confirmation not present in saved notes: {key}")
        source = record["raw_cells"][0]["provenance"]
        if source["source_sha256"] != entry["source_sha256"]:
            raise ValueError(f"Source identity mismatch: {key}")
        evidence_cells = [
            *record["raw_cells"],
            *record.get("conditions", {}).values(),
            *record.get("outcomes", []),
        ]
        if any(
            cell["provenance"].get("source_sha256") != entry["source_sha256"]
            or cell["provenance"].get("source_url") != source["source_url"]
            or cell["provenance"].get("file") != source["file"]
            for cell in evidence_cells
        ):
            raise ValueError(f"Field source identity mismatch: {key}")
        if Path(source["file"]).name != source["file"]:
            raise ValueError(f"Invalid source filename: {key}")
        source_path = root / "data/raw/preserved-review" / source["file"]
        if (
            not source_path.is_file()
            or hashlib.sha256(source_path.read_bytes()).hexdigest() != entry["source_sha256"]
        ):
            raise ValueError(f"Captured source missing or checksum mismatch: {key}")
        updated = copy.deepcopy(record)
        transformations: list[str] = []
        questions = [issue["message"] for issue in record.get("issues", [])]
        if key in {("PSI-25", "B3"), ("PSI-25", "B5")}:
            description = updated["conditions"]["material_description"]
            value = description["value"]
            expected = "100 micron film 2 cm wide" if key[1] == "B3" else "200 micron 2 cm wide"
            if " ".join(value.split()) != expected:
                raise ValueError(f"Reviewed source description changed: {key}")
            fields: list[tuple[str, float | str, str | None, str | None]] = [
                ("thickness_um", 100.0 if key[1] == "B3" else 200.0, "um", "micron"),
                ("width_cm", 2.0, "cm", "cm"),
            ]
            if key[1] == "B3":
                fields.insert(0, ("geometry", "film", None, None))
            for field, normalized, unit, original_unit in fields:
                updated["conditions"][field] = {
                    **copy.deepcopy(description),
                    "value": normalized,
                    "unit": unit,
                    "original_unit": original_unit,
                }
                transformations.append(f"reviewed correction: {field}")
            questions.append("Material identity unresolved; retain other source ambiguities.")
        if key == ("PSI-25", "B2"):
            questions.append("Final oxygen interpretation remains under review.")
        if key == ("PSI-25", "B4"):
            questions.append(
                "Interpretation of the negative initial CO reading remains under review."
            )
        if key == ("PSI-99", "SAFFIRE-II-2-4"):
            questions.append(
                "Thickness source literal 037 mm remains ambiguous; normalized value unresolved."
            )
        for outcome in updated.get("outcomes", []):
            if (
                outcome.get("qualifier") == "not_applicable_in_source"
                and (outcome.get("original_value") or "").strip().casefold() == "n/a"
            ):
                outcome["qualifier"] = "source_marker_meaning_unresolved"
                transformations.append(
                    f"preserve source marker semantics: {outcome['outcome_type']}"
                )
                questions.append("Meaning of source marker n/a needs source documentation.")
        EvidenceCandidate.model_validate(updated)
        fixtures.append(
            ReviewedEvidence(
                investigation_id=key[0],
                test_id=key[1],
                evidence_kind="background_table_row" if key[0] == "PSI-69" else "run",
                source_sha256=entry["source_sha256"],
                candidate_fingerprint=entry["candidate_fingerprint"],
                review_action=entry["proposed_action"],
                supporting_references=entry["supporting_references"],
                confirming_note=note,
                review_history=entry["review_history"],
                original_candidate=record,
                reviewed_candidate=updated,
                transformations=transformations,
                unresolved_questions=list(dict.fromkeys(questions)),
            )
        )
    if seen != set(candidates):
        raise ValueError("All captured review candidates require a reconciliation entry")
    return fixtures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/reviewed-evidence-v1.json")
    )
    parser.add_argument(
        "--decisions-output", type=Path, default=Path("data/processed/reviewed-decisions-v1.json")
    )
    args = parser.parse_args()
    fixtures = prepare(args.workspace)
    payload = {
        "schema_version": "reviewed-evidence-v1",
        "scope": "reviewed source transcriptions; unresolved questions retained",
        "records": [f.model_dump(mode="json") for f in fixtures],
    }
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    decisions = {
        "schema_version": "reviewed-decisions-v1",
        "fixture_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "decisions": [
            {
                "investigation_id": f.investigation_id,
                "test_id": f.test_id,
                "candidate_fingerprint": f.candidate_fingerprint,
                "source_sha256": f.source_sha256,
                "reviewed_fingerprint": fingerprint(f.reviewed_candidate),
                "action": {
                    "accept_extraction": "accept",
                    "correction_proposed": "correct",
                    "needs_research": "needs_research",
                }[f.review_action],
                "reviewer": f.confirming_note["reviewer"],
                "reviewed_at": f.confirming_note["saved_at_utc"],
                "rationale": f.confirming_note["note"],
                "supporting_references": f.supporting_references,
                "unresolved_questions": f.unresolved_questions,
            }
            for f in fixtures
        ],
    }
    decision_content = json.dumps(decisions, indent=2, ensure_ascii=False) + "\n"
    outputs = [(args.output, content), (args.decisions_output, decision_content)]
    if args.output.resolve() == args.decisions_output.resolve():
        parser.error("Output paths must be distinct")
    for path, text in outputs:
        if path.exists() and path.read_text(encoding="utf-8") != text:
            parser.error(f"Choose a new output path; existing artifact differs: {path}")
    for path, text in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    print(f"Prepared {len(fixtures)} reviewed evidence records: {args.output}")


if __name__ == "__main__":
    main()
