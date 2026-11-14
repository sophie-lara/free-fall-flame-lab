"""Bridge reviewed table evidence into retrieval (record cards) and coverage.

Implements the RAG side of docs/rag_adapter_handoff.md:

- Accepts `reviewed-evidence-v1.json` only with a matching `reviewed-decisions-v1.json`
  (exact-byte SHA-256), and each record only if its decision binds the same identity,
  source hash, candidate fingerprint and reviewed fingerprint, and the reviewed
  candidate validates as `EvidenceCandidate`. Anything else is rejected with a reason.
- Record cards quote source cells verbatim and keep derived values, review state,
  open questions and locators visibly separate. Answers can cite the cell text.
- Coverage records receive only values that convert faithfully (numeric value, known
  unit, no qualifier). Everything else is reported, never coerced or dropped silently.
- CSV records keep their record/column locators; no PDF page is invented (page 0 in
  the index means "no page").

    python -m combustion_atlas.analysis.evidence_bridge sync     # verify, report, index
    python -m combustion_atlas.analysis.evidence_bridge report   # verify and report only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from combustion_atlas.review.evidence_schema import EvidenceCandidate
from combustion_atlas.review.fixtures import fingerprint

EVIDENCE = Path("data/processed/reviewed-evidence-v1.json")
DECISIONS = Path("data/processed/reviewed-decisions-v1.json")
ACTION_LABELS = {
    "accept": "accepted",
    "correct": "corrected",
    "needs_research": "needs research",
}

# Canonical field -> (coverage key, {unit as written (lowercase): factor}). The None key
# applies when the unit is unset but implied by the field name itself.
CONDITION_MAP: dict[str, tuple[str, dict[str | None, float]]] = {
    "initial_oxygen": ("oxygen_pct", {"%": 1, "% by vol": 1, "vol%": 1, "% vol": 1}),
    "oxygen_percent": ("oxygen_pct", {"%": 1, "% by vol": 1, "vol%": 1, "% vol": 1}),
    "oxygen_pct": ("oxygen_pct", {"%": 1, None: 1}),
    "oxygen_mole_fraction": ("oxygen_pct", {"mole fraction": 100}),
    "airflow": ("flow_cm_s", {"cm/s": 1, "mm/s": 0.1}),
    "airflow_cm_s": ("flow_cm_s", {"cm/s": 1, None: 1}),
    "thickness_um": ("thickness_mm", {"um": 0.001, "µm": 0.001, "micron": 0.001, None: 0.001}),
    "thickness": ("thickness_mm", {"mm": 1, "cm": 10, "um": 0.001, "µm": 0.001}),
    "droplet_diameter": ("droplet_diameter_mm", {"mm": 1}),
}
OUTCOME_MAP: dict[str, tuple[str, dict[str | None, float]]] = {
    "burn_time": ("burn_time_s", {"s": 1, "min": 60}),
    "spread_rate_1g": ("spread_rate_1g_mm_s", {"mm/s": 1, "cm/s": 10}),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_reviewed(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verified reviewed records plus a report of everything rejected or unavailable."""
    evidence_path, decisions_path = root / EVIDENCE, root / DECISIONS
    report: dict[str, Any] = {"accepted": 0, "rejected": [], "warnings": []}
    if not evidence_path.is_file() or not decisions_path.is_file():
        report["warnings"].append(
            "Reviewed evidence and decisions files are not available locally "
            f"({EVIDENCE}, {DECISIONS})."
        )
        return [], report
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if decisions.get("fixture_sha256") != _sha256(evidence_path):
        report["rejected"].append(
            {"record": "*", "reason": "Decisions file does not match the evidence file bytes."}
        )
        return [], report
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    by_key = {
        (d["investigation_id"], d["test_id"], d["candidate_fingerprint"]): d
        for d in decisions.get("decisions", [])
    }
    accepted = []
    for item in evidence.get("records", []):
        name = f"{item.get('investigation_id')}/{item.get('test_id')}"
        decision = by_key.get(
            (item.get("investigation_id"), item.get("test_id"), item.get("candidate_fingerprint"))
        )
        reason = None
        if decision is None:
            reason = "No decision binds this record's identity and candidate fingerprint."
        elif decision.get("source_sha256") != item.get("source_sha256"):
            reason = "Decision and record name different source files."
        elif decision.get("reviewed_fingerprint") != fingerprint(item["reviewed_candidate"]):
            reason = "Reviewed candidate changed after its decision."
        if reason is None:
            try:
                candidate = EvidenceCandidate.model_validate(item["reviewed_candidate"])
            except ValidationError as exc:
                reason = (
                    f"Reviewed candidate is not a valid EvidenceCandidate: {exc.errors()[0]['msg']}"
                )
        if reason is not None:
            report["rejected"].append({"record": name, "reason": reason})
            continue
        assert decision is not None
        accepted.append(
            {
                "evidence": item,
                "candidate": candidate,
                "decision": decision,
                "review_action": ACTION_LABELS.get(decision.get("action"), decision.get("action")),
            }
        )
    report["accepted"] = len(accepted)
    return accepted, report


def _convert(
    value: Any,
    canonical: str,
    table: dict[str, tuple[str, dict[str | None, float]]],
    record: str,
    report: list[dict[str, Any]],
) -> tuple[str, float] | None:
    if canonical not in table:
        return None
    key, units = table[canonical]
    problem = None
    if value.qualifier:
        problem = f"qualifier '{value.qualifier}' kept as text"
    elif not isinstance(value.value, int | float) or isinstance(value.value, bool):
        problem = f"non-numeric value {value.value!r}"
    elif not math.isfinite(float(value.value)):
        problem = "non-finite value"
    else:
        unit = value.unit.strip().lower() if value.unit else None
        if unit not in units:
            problem = f"unit {value.unit!r} not recognized for {canonical}"
        else:
            return key, float(value.value) * units[unit]
    report.append(
        {"record": record, "field": canonical, "original": value.original_value, "reason": problem}
    )
    return None


def _locator(location: Any) -> str:
    if location.page:
        table = f", table {location.table}" if location.table else ""
        return f"{location.file}, PDF page {location.page}{table}, row {location.row}"
    return f"{location.file}, CSV record {location.row}, column {location.column!r}"


def to_card(record: dict[str, Any]) -> dict[str, Any]:
    candidate: EvidenceCandidate = record["candidate"]
    item, decision = record["evidence"], record["decision"]
    identity = candidate.identity
    lines = [
        f"Structured table record — {identity.investigation_id} test {identity.test_id}"
        + (
            " (background study row, not a flight run)"
            if item.get("evidence_kind") == "background_table_row"
            else ""
        ),
        f"Review: {record['review_action']}; transcription status {candidate.human_review_status}.",
        "Source cells (verbatim):",
    ]
    for cell in candidate.raw_cells:
        unit = f" [{cell.original_unit}]" if cell.original_unit else ""
        lines.append(f"- {cell.provenance.column}: {cell.original_value}{unit}")
    derived = [
        f"- {name} = {value.value}{' ' + value.unit if value.unit else ''}"
        + (f" ({value.qualifier})" if value.qualifier else "")
        for name, value in candidate.conditions.items()
    ] + [
        f"- {o.outcome_type} = {o.value}{' ' + o.unit if o.unit else ''}"
        + (f" ({o.qualifier})" if o.qualifier else "")
        for o in candidate.outcomes
    ]
    if derived:
        lines += ["Derived values (interpretations, not source text):", *derived]
    questions = item.get("unresolved_questions") or decision.get("unresolved_questions") or []
    if questions:
        lines += ["Open questions:", *[f"- {q}" for q in questions]]
    if candidate.issues:
        lines += ["Issues:", *[f"- {i.field}: {i.message}" for i in candidate.issues]]
    first = candidate.raw_cells[0].provenance if candidate.raw_cells else None
    if first is not None:
        lines.append(f"Source: {_locator(first)}")
    text = "\n".join(lines)
    card_fingerprint = fingerprint({"text": text, "decision": decision})
    return {
        "card_id": f"card:{identity.investigation_id}:{identity.test_id}:{card_fingerprint[:12]}",
        "fingerprint": card_fingerprint,
        "source_id": item["source_sha256"][:16],
        "source_sha256": item["source_sha256"],
        "filename": first.file if first else "reviewed-evidence",
        "source_url": first.source_url if first else None,
        "investigation_id": identity.investigation_id,
        "physical_page": first.page if first and first.page else 0,
        "text": text,
        "meta": {
            "investigation_id": identity.investigation_id,
            "test_id": identity.test_id,
            "evidence_kind": item.get("evidence_kind"),
            "review_action": record["review_action"],
            "transcription_status": candidate.human_review_status,
            "open_questions": len(questions),
            "locator": _locator(first) if first else None,
        },
    }


def to_coverage(record: dict[str, Any], report: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Coverage fields from faithful conversions; background rows are not runs."""
    item, candidate = record["evidence"], record["candidate"]
    if item.get("evidence_kind") != "run":
        return None
    name = f"{candidate.identity.investigation_id}/{candidate.identity.test_id}"
    fields: dict[str, float] = {}
    for canonical, value in candidate.conditions.items():
        converted = _convert(value, canonical, CONDITION_MAP, name, report)
        if converted:
            fields[converted[0]] = converted[1]
    outcomes = {}
    for outcome in candidate.outcomes:
        converted = _convert(outcome, outcome.outcome_type, OUTCOME_MAP, name, report)
        if converted:
            outcomes[converted[0]] = {
                "value": converted[1],
                "raw": outcome.original_value or "",
                "unit": None,
            }
    material = candidate.conditions.get("material") or candidate.conditions.get(
        "material_description"
    )
    return {
        "investigation_id": candidate.identity.investigation_id,
        "test_id": candidate.identity.test_id,
        "fields": fields,
        "outcomes": outcomes,
        "material": material.value if material and isinstance(material.value, str) else None,
        "review_action": record["review_action"],
    }


def coverage_overrides(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records, report = load_reviewed(root)
    conversion: list[dict[str, Any]] = []
    overrides = [c for r in records if (c := to_coverage(r, conversion))]
    report["unconverted"] = conversion
    return overrides, report


def sync_cards(store: Any, cards: list[dict[str, Any]]) -> dict[str, int]:
    """Make the indexed record cards exactly match `cards`; other chunks untouched."""
    connection = store.connection
    connection.execute(
        "CREATE TABLE IF NOT EXISTS record_cards ("
        "card_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, payload TEXT NOT NULL)"
    )
    existing = {
        r[0]: r[1] for r in connection.execute("SELECT card_id, fingerprint FROM record_cards")
    }
    wanted = {c["card_id"]: c for c in cards}
    stale = [
        cid for cid, fp in existing.items() if cid not in wanted or wanted[cid]["fingerprint"] != fp
    ]
    added = 0
    with connection:
        for cid in stale:
            for table in ("vectors", "chunks_fts", "chunks"):
                connection.execute(f"DELETE FROM {table} WHERE chunk_id=?", (cid,))
            connection.execute("DELETE FROM record_cards WHERE card_id=?", (cid,))
        for cid, card in wanted.items():
            if cid in existing and cid not in stale:
                continue
            connection.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cid,
                    card["source_id"],
                    card["investigation_id"],
                    card["filename"],
                    card["source_url"],
                    card["source_sha256"],
                    card["physical_page"],
                    0,
                    0,
                    len(card["text"]),
                    card["text"],
                ),
            )
            connection.execute("INSERT INTO chunks_fts VALUES (?, ?)", (cid, card["text"]))
            connection.execute(
                "INSERT INTO record_cards VALUES (?, ?, ?)",
                (cid, card["fingerprint"], json.dumps(card["meta"], ensure_ascii=False)),
            )
            added += 1
    return {
        "cards": len(wanted),
        "added_or_changed": added,
        "removed": len([c for c in stale if c not in wanted]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["sync", "report"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--database", type=Path, default=Path("data/embeddings/rag.sqlite3"))
    args = parser.parse_args(argv)
    records, report = load_reviewed(args.root)
    conversion: list[dict[str, Any]] = []
    report["coverage_runs"] = sum(1 for r in records if to_coverage(r, conversion))
    report["unconverted"] = conversion
    if args.command == "sync":
        from combustion_atlas.rag.store import DocumentStore

        with DocumentStore(args.database) as store:
            report["index"] = sync_cards(store, [to_card(r) for r in records])
        report["next_step"] = (
            "Embed new cards: providers embed --missing-only --allow-provider-calls"
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
