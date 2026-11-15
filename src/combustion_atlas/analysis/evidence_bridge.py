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
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from combustion_atlas.review.evidence_schema import EvidenceCandidate
from combustion_atlas.review.fixtures import fingerprint

EVIDENCE = Path("data/processed/reviewed-evidence-v1.json")
DECISIONS = Path("data/processed/reviewed-decisions-v1.json")
PROCESSED = Path("data/processed")
# Notes that make a value unsafe for filterable numbers (it stays on the card).
EXCLUDING_NOTES = {"unresolved", "ambiguous", "pending", "inferred"}
PLAIN_NUMBER = re.compile(r"^\d+(\.\d+)?$")
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
    "thickness": ("thickness_mm", {"mm": 1, "cm": 10, "um": 0.001, "µm": 0.001, "micron": 0.001}),
    "droplet_diameter": ("droplet_diameter_mm", {"mm": 1}),
}
OUTCOME_MAP: dict[str, tuple[str, dict[str | None, float]]] = {
    "burn_time": ("burn_time_s", {"s": 1, "min": 60}),
    "spread_rate_1g": ("spread_rate_1g_mm_s", {"mm/s": 1, "cm/s": 10}),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_pairs(root: Path) -> list[tuple[Path, Path]]:
    """Every reviewed-evidence*.json with its matching reviewed-decisions*.json."""
    pairs = []
    for evidence in sorted((root / PROCESSED).glob("reviewed-evidence*.json")):
        suffix = evidence.name.removeprefix("reviewed-evidence")
        pairs.append((evidence, evidence.with_name(f"reviewed-decisions{suffix}")))
    return pairs


def _load_pair(
    evidence_path: Path, decisions_path: Path, report: dict[str, Any]
) -> list[dict[str, Any]]:
    label = evidence_path.name
    if not decisions_path.is_file():
        report["rejected"].append({"record": label, "reason": "No matching decisions file."})
        return []
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if evidence.get("draft") or decisions.get("draft"):
        report["rejected"].append({"record": label, "reason": "File pair is marked draft."})
        return []
    if decisions.get("fixture_sha256") != _sha256(evidence_path):
        report["rejected"].append(
            {"record": label, "reason": "Decisions file does not match the evidence file bytes."}
        )
        return []
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
            report["rejected"].append({"record": name, "reason": reason, "file": label})
            continue
        assert decision is not None
        pattern_only = bool(
            (item.get("confirming_note") or {}).get("pattern_rule_only")
            or decision.get("pattern_rule_only")
        )
        action = ACTION_LABELS.get(decision.get("action"), decision.get("action"))
        accepted.append(
            {
                "evidence": item,
                "candidate": candidate,
                "decision": decision,
                "pattern_rule_only": pattern_only,
                "review_action": "not individually reviewed" if pattern_only else action,
                "file": label,
            }
        )
    return accepted


def load_reviewed(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verified reviewed records from every file pair, plus a report of rejections."""
    report: dict[str, Any] = {"accepted": 0, "rejected": [], "warnings": [], "files": []}
    pairs = evidence_pairs(root)
    if not pairs:
        report["warnings"].append(
            f"No reviewed evidence files found under {PROCESSED} (reviewed-evidence*.json)."
        )
        return [], report
    records: list[dict[str, Any]] = []
    for evidence_path, decisions_path in pairs:
        loaded = _load_pair(evidence_path, decisions_path, report)
        report["files"].append({"file": evidence_path.name, "accepted": len(loaded)})
        records.extend(loaded)
    keys = [
        (r["candidate"].identity.investigation_id, r["candidate"].identity.test_id) for r in records
    ]
    duplicates = {k for k in keys if keys.count(k) > 1}
    for key in sorted(duplicates):
        report["rejected"].append(
            {"record": "/".join(key), "reason": "Identity appears in more than one file."}
        )
    records = [r for r, k in zip(records, keys, strict=True) if k not in duplicates]
    report["accepted"] = len(records)
    return records, report


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str) and PLAIN_NUMBER.fullmatch(value.strip()):
        return float(value.strip())
    return None


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
    blocking = sorted({n.kind for n in value.notes} & EXCLUDING_NOTES)
    number = _number(value.value)
    problem = None
    if blocking:
        problem = f"note ({', '.join(blocking)}) keeps it out of filterable numbers"
    elif value.qualifier:
        problem = f"qualifier '{value.qualifier}' kept as text"
    elif number is None:
        problem = f"non-numeric value {value.value!r}"
    else:
        unit = value.unit.strip().lower() if value.unit else None
        if unit not in units:
            problem = f"unit {value.unit!r} not recognized for {canonical}"
        else:
            return key, number * units[unit]
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
        + {
            "background_table_row": " (background study row, not a flight run)",
            "planned_test_condition": " (planned test condition from a test matrix, "
            "not an observed result)",
        }.get(item.get("evidence_kind") or "", ""),
        f"Review: {record['review_action']}; transcription status "
        f"{candidate.human_review_status}."
        + (
            " A reviewer's rule was applied to this row by pattern; the row itself was not checked."
            if record.get("pattern_rule_only")
            else ""
        ),
        "Source cells (verbatim):",
    ]
    for cell in candidate.raw_cells:
        unit = f" [{cell.original_unit}]" if cell.original_unit else ""
        lines.append(f"- {cell.provenance.column}: {cell.original_value}{unit}")

    def value_lines(name: str, value: Any) -> list[str]:
        unit = f" {value.unit}" if value.unit else ""
        qualifier = f" ({value.qualifier})" if value.qualifier else ""
        out = [f"- {name} = {value.value}{unit}{qualifier}"]
        for note in value.notes:
            who = [] if note.by == note.kind else [note.by]
            who += [note.decision] if note.decision else []
            by = f", {' '.join(who)}" if who else ""
            out.append(f"  note ({note.kind}{by}): {note.text}")
        return out

    derived = [line for name, v in candidate.conditions.items() for line in value_lines(name, v)]
    derived += [line for o in candidate.outcomes for line in value_lines(o.outcome_type, o)]
    if derived:
        lines += ["Derived values (interpretations, not source text):", *derived]
    if candidate.additional_fields:
        lines.append("Additional source content (not mapped to a field):")
        for name, value in candidate.additional_fields.items():
            lines += value_lines(name, value)
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
            "pattern_rule_only": bool(record.get("pattern_rule_only")),
            "transcription_status": candidate.human_review_status,
            "notes": sum(
                len(v.notes)
                for v in [
                    *candidate.conditions.values(),
                    *candidate.outcomes,
                    *candidate.additional_fields.values(),
                ]
            ),
            "open_questions": len(questions),
            "locator": _locator(first) if first else None,
        },
    }


def to_coverage(record: dict[str, Any], report: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Coverage fields from faithful conversions; background rows are not runs."""
    item, candidate = record["evidence"], record["candidate"]
    if item.get("evidence_kind") != "run" or record.get("pattern_rule_only"):
        return None  # background rows are not runs; pattern-only rows were not checked
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


ATM_TO_KPA = 101.325


def to_proposed(record: dict[str, Any]) -> dict[str, Any] | None:
    """A proposed (planned) test as a separate coverage layer; never a run, never a gap.

    Converts atm to kPa and mole fractions to percent, and lists every conversion. Values
    with ambiguous/unresolved notes (e.g. an unassigned droplet diameter) are left off.
    """
    item, candidate = record["evidence"], record["candidate"]
    if item.get("evidence_kind") != "planned_test_condition":
        return None
    fields: dict[str, float] = {}
    conversions: list[str] = []
    omitted: list[str] = []
    conditions = candidate.conditions
    suppressant = str(getattr(conditions.get("suppressant"), "value", "") or "")

    def number(name: str) -> float | None:
        value = conditions.get(name)
        if value is None:
            return None
        if {n.kind for n in value.notes} & EXCLUDING_NOTES:
            omitted.append(f"{name} ({value.original_value}): see its note")
            return None
        return _number(value.value)

    pressure = number("pressure")
    if pressure is not None and (conditions["pressure"].unit or "").lower() == "atm":
        fields["pressure_kpa"] = round(pressure * ATM_TO_KPA, 3)
        conversions.append(f"pressure {pressure:g} atm → {fields['pressure_kpa']:g} kPa")
    oxygen = number("oxygen_mole_fraction")
    if oxygen is not None:
        fields["oxygen_pct"] = round(oxygen * 100, 6)
        conversions.append(f"oxygen mole fraction {oxygen:g} → {fields['oxygen_pct']:g} %")
    fraction = number("suppressant_mole_fraction")
    if fraction is not None and suppressant.strip().lower() in {"he", "helium"}:
        fields["helium_pct"] = round(fraction * 100, 6)
        conversions.append(f"He mole fraction {fraction:g} → {fields['helium_pct']:g} %")
    flow = number("flow_velocity")
    if flow is not None and (conditions["flow_velocity"].unit or "").lower() == "cm/s":
        fields["flow_cm_s"] = flow
    number("droplet_diameter")  # recorded under `omitted` when ambiguous
    first = candidate.raw_cells[0].provenance
    return {
        "investigation_id": candidate.identity.investigation_id,
        "test_id": candidate.identity.test_id,
        "table": first.table,
        "page": first.page,
        "file": first.file,
        "source_url": first.source_url,  # NASA PSI investigation page
        # Captured PDF, served by /api/documents/<id>.
        "document_id": (item.get("source_sha256") or first.source_sha256 or "")[:16] or None,
        "fields": fields,
        "fuel": str(getattr(conditions.get("fuel"), "value", "") or "") or None,
        "suppressant": suppressant or None,
        "conversions": conversions,
        "omitted": omitted,
        "caveats": [
            i.message
            for i in candidate.issues
            if i.code in {"evidence_class", "preliminary_test_matrix"}
        ],
    }


def proposed_tests(root: Path) -> list[dict[str, Any]]:
    records, _ = load_reviewed(root)
    return [p for r in records if (p := to_proposed(r))]


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

        from .table_index import build, sync_rows

        # One card per source table in the text index; rows go to the structured
        # row index so exact-value questions can still reach them.
        cards, rows = build(records)
        with DocumentStore(args.database) as store:
            report["index"] = sync_cards(store, cards)
            report["index"].update(sync_rows(store, rows))
        report["next_step"] = (
            "Embed new cards: providers embed --missing-only --allow-provider-calls"
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
