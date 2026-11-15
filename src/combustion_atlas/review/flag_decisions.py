"""Apply recorded flag-review decisions to imported model review candidates.

The decision spec (JSON, versioned next to its human-readable review document) names
each decision, its status and the exact candidates it covers. Each decided rule edits
a copy of the candidate and attaches visible notes saying where a value was assumed,
inferred, ambiguous or unresolved. The original candidate is kept unchanged alongside
the reviewed one. Pending decisions leave affected records as ``needs_research``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from .evidence_schema import EvidenceCandidate, ValueNote
from .fixtures import ReviewedEvidence, fingerprint

SPEC_SCHEMA = "flag-decisions-v1"
FSM = "Fuel Sample Material"
DIMENSION = re.compile(r"(?<![\w/.])(\d+(?:\.\d+)?)\s*(cm|mm|micron|um|µm)\b", re.I)
ROD_DIMENSION = re.compile(r"(?<![\w/.])(\d+/\d+|\d*\.\d+|\d+)\s*(\"|in\b|inch(?:es)?\b)?", re.I)
UNRESOLVED_KINDS = {"ambiguous", "unresolved", "pending"}


class Context:
    def __init__(self, candidate: dict[str, Any], decision_id: str) -> None:
        self.c = candidate
        self.decision = decision_id
        self.transformations: list[str] = []
        self.questions: list[str] = []

    def note(self, value: dict[str, Any], kind: str, text: str) -> None:
        item = ValueNote.model_validate(
            {"kind": kind, "text": text, "by": "reviewer", "decision": self.decision}
        )
        value.setdefault("notes", []).append(item.model_dump(mode="json"))

    def log(self, text: str) -> None:
        self.transformations.append(f"{self.decision}: {text}")

    def fsm_text(self) -> str:
        for cell in self.c["raw_cells"]:
            if cell["provenance"]["column"] == FSM:
                return cell["original_value"] or ""
        raise ValueError(f"No {FSM} cell: {self.c['identity']}")

    def fsm_cell(self) -> dict[str, Any]:
        for cell in self.c["raw_cells"]:
            if cell["provenance"]["column"] == FSM:
                return cast(dict[str, Any], cell)
        raise ValueError(f"No {FSM} cell: {self.c['identity']}")

    def from_fsm(self, value: dict[str, Any]) -> bool:
        return bool(value["provenance"]["column"] == FSM)

    def drop_condition(self, name: str) -> None:
        value = self.c["conditions"].get(name)
        if value is not None and self.from_fsm(value):
            del self.c["conditions"][name]
            self.log(f"removed {name}={value['value']!r} {value.get('unit') or ''}".rstrip())

    def drop_unmapped_fsm(self) -> None:
        for key in [k for k in self.c["extra_metadata"] if k.startswith("unmapped_")]:
            if self.c["extra_metadata"][key]["provenance"]["column"] == FSM:
                del self.c["extra_metadata"][key]
                self.log(f"moved unmapped {FSM} remainder ({key}) to additional_fields")

    def add_additional(self, key: str, value: Any, unit: str | None, kind: str, text: str) -> None:
        entry = {
            **copy.deepcopy(self.fsm_cell()),
            "value": value,
            "unit": unit,
            "qualifier": None,
            "uncertainty": None,
            "notes": [],
        }
        self.note(entry, kind, text)
        self.c.setdefault("additional_fields", {})[key] = entry
        self.log(f"added additional_fields.{key}={value!r} {unit or ''}".rstrip())

    def set_dimension(self, name: str, number: float, unit: str, kind: str, text: str) -> None:
        entry = {
            **copy.deepcopy(self.fsm_cell()),
            "value": number,
            "unit": unit,
            "qualifier": None,
            "uncertainty": None,
            "notes": [],
        }
        self.note(entry, kind, text)
        self.c["conditions"][name] = entry
        self.log(f"assigned {name}={number} {unit}")

    def outcome(self, name: str) -> dict[str, Any] | None:
        return next((o for o in self.c["outcomes"] if o["outcome_type"] == name), None)


def normalize_number(ctx: Context, name: str, value: dict[str, Any]) -> None:
    """Fix values like '2 cm' with unit 'cm' (unit stated twice) and numeric strings."""
    raw = value.get("value")
    if not isinstance(raw, str):
        return
    text = raw.strip()
    unit = (value.get("unit") or "").strip()
    if unit and text.casefold().endswith(unit.casefold()):
        text = text[: -len(unit)].strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        value["value"] = float(text)
        ctx.log(f"normalized {name} value {raw!r} -> {value['value']}")


def unlabeled_assumed(ctx: Context, text: str) -> None:
    for name in ("width", "thickness"):
        value = ctx.c["conditions"].get(name)
        if value is None or not ctx.from_fsm(value):
            continue
        normalize_number(ctx, name, value)
        label = "wide" if name == "width" else "thick"
        if not re.search(rf"\b{label}\b", text, re.I):
            ctx.note(
                value,
                "assumed",
                f"Source cell '{text}' does not label this dimension; the cm value is taken "
                "as width and the mm/micron value as thickness from context.",
            )


def rule_d1(ctx: Context) -> None:
    """Two unlabeled dimensions: accept width (cm) / thickness (mm, micron) with a note."""
    text = ctx.fsm_text()
    for name in ("width", "thickness"):
        if name not in ctx.c["conditions"]:
            raise ValueError(f"D1 expects proposed {name}: {ctx.c['identity']}")
    unlabeled_assumed(ctx, text)


def rule_d2(ctx: Context) -> None:
    """One unlabeled dimension: do not force a field; keep it as an unresolved extra."""
    text = ctx.fsm_text()
    dims = DIMENSION.findall(text)
    if len(dims) != 1:
        raise ValueError(f"D2 expects one dimension in {text!r}")
    number, unit = dims[0]
    for name in ("width", "thickness", "length", "diameter"):
        ctx.drop_condition(name)
    ctx.drop_unmapped_fsm()
    ctx.add_additional(
        "unlabeled_dimension",
        float(number),
        unit,
        "unresolved",
        f"Source cell '{text}' gives one unlabeled dimension ({number} {unit}). "
        "It is unclear what it measures (e.g. width, length or diameter), so it is not "
        "assigned to a field.",
    )
    ctx.questions.append(f"Meaning of the unlabeled {number} {unit} dimension is unresolved.")


def rule_d3(ctx: Context) -> None:
    """Rods: material only if named; inch dimension kept as an unresolved extra."""
    text = ctx.fsm_text()
    material = ctx.c["conditions"].get("material")
    if material is not None and ctx.from_fsm(material):
        named = material.get("value")
        if not named or str(named).casefold() not in text.casefold():
            ctx.drop_condition("material")
    if "material" not in ctx.c["conditions"]:
        description = ctx.c["conditions"].get("material_description")
        if description is not None:
            ctx.note(
                description,
                "unresolved",
                "The source names no material; it is not inferred (a clear or black rod is "
                "not assumed to be PMMA).",
            )
    match = ROD_DIMENSION.search(text)
    if not match:
        raise ValueError(f"D3 expects a rod dimension in {text!r}")
    number, mark = match.group(1), match.group(2)
    ctx.drop_condition("width")
    ctx.drop_unmapped_fsm()
    unit_text = (
        "inches"
        if mark
        else "no unit given (inches by analogy with the other rod rows, not stated here)"
    )
    ctx.add_additional(
        "rod_dimension",
        number,
        "in" if mark else None,
        "unresolved",
        f"Source cell '{text}' gives one rod dimension ({number}; {unit_text}). It is "
        "probably the rod diameter, but the source does not say, so it is not assigned to "
        "width or thickness.",
    )


def rule_d4(ctx: Context) -> None:
    """Labeled dimensions: accept as proposed; apply the D1 width context where needed."""
    text = ctx.fsm_text()
    unlabeled_assumed(ctx, text)
    if "width" not in ctx.c["conditions"]:
        match = re.search(r"(\d+(?:\.\d+)?)\s*cm\b(\s+2ide\b)?", text, re.I)
        if match:
            typo = bool(match.group(2))
            ctx.drop_unmapped_fsm()
            ctx.set_dimension(
                "width",
                float(match.group(1)),
                "cm",
                "assumed",
                (
                    f"Source cell '{text}' reads '2ide'; taken as a typo for 'wide'."
                    if typo
                    else f"Source cell '{text}' does not label the cm dimension; taken as "
                    "width from context, as for the other BASS film/slab rows."
                ),
            )


def rule_d5(ctx: Context) -> None:
    """Saffire '?-g' columns: accept, interpretation unresolved."""
    for name, header in (
        ("burn_length_unspecified_gravity", "?-g Burn Length"),
        ("spread_length_unspecified_gravity", "?-g Spread Length"),
    ):
        value = ctx.outcome(name)
        if value is None:
            continue
        ctx.note(
            value,
            "ambiguous",
            f"The source column header '{header}' does not state the gravity level.",
        )
        unit = (value.get("unit") or "").strip().casefold()
        if name.startswith("spread_length") and unit.endswith("/s"):
            ctx.note(
                value,
                "ambiguous",
                f"Reported in {value['unit']}, a rate unit, under a 'Spread Length' header.",
            )
    ctx.questions.append("Gravity level of the Saffire-II '?-g' columns is unresolved.")


def rule_d6(ctx: Context) -> None:
    """CO markers: keep as written with a likely-meaning note."""
    candidates = [ctx.c["conditions"].get("initial_co"), ctx.outcome("final_co")]
    found = False
    for value in [v for v in candidates if v is not None]:
        raw = (value.get("original_value") or "").strip()
        if raw.casefold() not in {"or", "over"}:
            continue
        found = True
        ctx.note(
            value,
            "unresolved",
            f"Source value '{raw}' kept as written. It likely means the reading was over or "
            "out of range, but the source does not define it; there is no numeric value.",
        )
    if not found:
        raise ValueError(f"D6 found no OR/over CO marker: {ctx.c['identity']}")


def rule_d7(ctx: Context) -> None:
    """Saffire thickness: note the 037 inference; leave the figure reference pending."""
    value = ctx.c["conditions"].get("thickness")
    if value is None:
        raise ValueError(f"D7 expects thickness: {ctx.c['identity']}")
    raw = (value.get("original_value") or "").strip()
    if raw.startswith("037"):
        ctx.note(
            value,
            "inferred",
            "Source reads '037 mm'. This is likely 0.37 mm with the decimal point missing; "
            "0.37 is our inference, not a source value.",
        )
    elif "fig" in raw.casefold():
        ctx.note(
            value,
            "pending",
            f"Source reads '{raw}': the thickness is only given in a figure of the source "
            "paper and has not been looked up yet.",
        )
        ctx.questions.append(f"Thickness pending: check '{raw}' in the source paper.")
    else:
        raise ValueError(f"D7 unexpected thickness {raw!r}")


def rule_d8(ctx: Context) -> None:
    """Keep geometry 'film' added by the importer's rule-based parser."""
    value = ctx.c["conditions"].get("geometry")
    text = ctx.fsm_text()
    if value is None or value.get("value") != "film" or "film" not in text.casefold():
        raise ValueError(f"D8 expects importer geometry 'film': {ctx.c['identity']}")
    ctx.note(
        value,
        "inferred",
        f"Geometry 'film' was added by the importer's rule-based parser (the model did not "
        f"propose it); the word appears in the source cell '{text}'.",
    )


RULES: dict[str, Callable[[Context], None]] = {
    "D1": rule_d1,
    "D2": rule_d2,
    "D3": rule_d3,
    "D4": rule_d4,
    "D5": rule_d5,
    "D6": rule_d6,
    "D7": rule_d7,
    "D8": rule_d8,
}


def model_notes(candidate: dict[str, Any]) -> None:
    """Surface each model note as a visible note on its value."""
    values = [*candidate["conditions"].values(), *candidate["outcomes"]]
    for value in values:
        text = value.get("uncertainty")
        if isinstance(text, str) and text.strip():
            notes = value.setdefault("notes", [])
            # The importer marks its own rule-based values; everything else is the model's.
            by = "pipeline" if text == "Deterministic extraction" else "model"
            if not any(n["by"] == by and n["text"] == text for n in notes):
                notes.insert(0, {"kind": "model", "text": text, "by": by, "decision": None})


def load_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != SPEC_SCHEMA:
        raise ValueError("Unsupported decision spec")
    for key, decision in spec["decisions"].items():
        if decision["status"] not in {"decided", "pending"}:
            raise ValueError(f"Unknown status for {key}")
        if decision["status"] == "decided" and key not in RULES and decision.get("tests"):
            raise ValueError(f"No rule implements decided {key}")
    return cast(dict[str, Any], spec)


def apply(
    root: Path, spec_path: Path, *, draft: bool = False
) -> tuple[list[ReviewedEvidence], dict[str, Any]]:
    spec = load_spec(spec_path)
    reviewer = (spec.get("reviewer") or "").strip()
    reviewed_at = spec.get("reviewed_at")
    if not draft and (not reviewer or not reviewed_at):
        raise ValueError("Decision spec needs reviewer and reviewed_at (or use --draft)")
    if reviewed_at:
        stamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError("reviewed_at requires a timezone")
    candidates_path = root / spec["candidates_file"]
    raw = candidates_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec["candidates_sha256"]:
        raise ValueError("Candidate file differs from the reviewed one")
    envelope = json.loads(raw)
    if envelope.get("schema_version") != "model-review-candidates-v2":
        raise ValueError("Requires a model-review-candidates-v2 envelope")
    run = root / spec["run_dir"]
    index_bytes = (run / "review-index.json").read_bytes()
    if hashlib.sha256(index_bytes).hexdigest() != spec["review_index_sha256"]:
        raise ValueError("Run review index differs from the reviewed one")
    results = {json.dumps(m["identity"], sort_keys=True): m for m in envelope["model_results"]}
    index = json.loads(index_bytes)
    result_paths = {
        (e["record"]["investigation_id"], e["record"]["test_id"]): e for e in index["records"]
    }
    document = root / spec["decision_document"]
    document_sha = hashlib.sha256(document.read_bytes()).hexdigest()
    spec_sha = hashlib.sha256(spec_path.read_bytes()).hexdigest()

    by_test: dict[tuple[str, str], list[str]] = {}
    for key, decision in spec["decisions"].items():
        for test in decision.get("tests", []):
            investigation, test_id = test.split("/", 1)
            by_test.setdefault((investigation, test_id), []).append(key)
    # Rows with the same pattern that no reviewer looked at individually: the decided
    # rule is applied for consistency, but the row stays unreviewed.
    by_pattern: set[tuple[str, str]] = set()
    for key, decision in spec["decisions"].items():
        for test in decision.get("pattern_tests", []):
            if decision["status"] != "decided":
                raise ValueError(f"pattern_tests require a decided rule: {key}")
            investigation, test_id = test.split("/", 1)
            if (investigation, test_id) in by_test:
                raise ValueError(f"{test} is listed as both reviewed and pattern-only")
            by_test.setdefault((investigation, test_id), []).append(key)
            by_pattern.add((investigation, test_id))

    records = {
        (r["identity"]["investigation_id"], r["identity"]["test_id"]): r
        for r in envelope["records"]
    }
    missing = set(by_test) - set(records)
    if missing:
        raise ValueError(f"Decisions name candidates not in the file: {sorted(missing)}")

    out: list[ReviewedEvidence] = []
    for key, decision_ids in sorted(
        by_test.items(), key=lambda kv: records[kv[0]]["raw_cells"][0]["provenance"]["row"]
    ):
        record = records[key]
        EvidenceCandidate.model_validate(record)
        identity = json.dumps(record["identity"], sort_keys=True)
        entry = result_paths.get(key)
        sidecar = results.get(identity)
        if entry is None or sidecar is None or sidecar["sha256"] != entry["result_sha256"]:
            raise ValueError(f"Model result binding mismatch: {key}")
        actual = hashlib.sha256((run / entry["result_path"]).read_bytes()).hexdigest()
        if actual != entry["result_sha256"]:
            raise ValueError(f"Model result file changed: {key}")
        updated = copy.deepcopy(record)
        model_notes(updated)
        transformations: list[str] = []
        questions: list[str] = []
        pending = []
        for decision_id in decision_ids:
            decision = spec["decisions"][decision_id]
            if decision["status"] == "pending":
                pending.append(decision_id)
                questions.append(f"{decision_id} pending: {decision['topic']}")
                ctx = Context(updated, decision_id)
                for field in decision.get("fields", []):
                    value = updated["conditions"].get(field)
                    if value is not None:
                        ctx.note(value, "pending", f"Awaiting review decision: {decision['topic']}")
                continue
            ctx = Context(updated, decision_id)
            RULES[decision_id](ctx)
            transformations += ctx.transformations
            questions += ctx.questions
        notes = [
            n
            for v in [
                *updated["conditions"].values(),
                *updated["outcomes"],
                *updated.get("additional_fields", {}).values(),
            ]
            for n in v.get("notes", [])
        ]
        unresolved = any(n["kind"] in UNRESOLVED_KINDS for n in notes)
        changed = any(
            t.split(": ", 1)[1].startswith(("removed", "assigned", "added", "moved"))
            for t in transformations
        )
        pattern_only = key in by_pattern
        if pattern_only:
            questions.append(
                "Row not individually reviewed: "
                + ", ".join(decision_ids)
                + " applied by pattern rule; other values unchecked."
            )
        action: Literal["accept_extraction", "correction_proposed", "needs_research"]
        if pending or any(n["kind"] == "pending" for n in notes):
            action = "needs_research"
            updated["human_review_status"] = "unreviewed"
        elif pattern_only:
            action = "correction_proposed" if changed else "accept_extraction"
            updated["human_review_status"] = "unreviewed"
        elif changed:
            action = "correction_proposed"
            updated["human_review_status"] = "corrected"
        else:
            action = "accept_extraction"
            updated["human_review_status"] = "accepted"
        updated["validation_status"] = (
            "review_required" if unresolved or pending or pattern_only else "validated"
        )
        updated["issues"].append(
            {
                "code": "review_decisions",
                "field": "Record",
                "message": "Flag review decisions applied: "
                + ", ".join(decision_ids)
                + f" (see {spec['decision_document']}). Notes on each value record "
                "assumptions and unresolved interpretations.",
                "severity": "review",
            }
        )
        EvidenceCandidate.model_validate(updated)
        source = record["raw_cells"][0]["provenance"]
        reference = (
            f"{source['file']} CSV record {source['row']} · Test {key[1]} ; {source['source_url']}"
        )
        rationale = " | ".join(f"{d}: {spec['decisions'][d]['rationale']}" for d in decision_ids)
        out.append(
            ReviewedEvidence(
                investigation_id=key[0],
                test_id=key[1],
                evidence_kind="run",
                source_sha256=source["source_sha256"],
                candidate_fingerprint=fingerprint(record),
                review_action=action,
                supporting_references=[reference],
                confirming_note={
                    "investigation_id": key[0],
                    "test_id": key[1],
                    "reviewer": reviewer or None,
                    "decision": action,
                    "decisions": decision_ids,
                    "note": rationale,
                    "saved_at_utc": reviewed_at,
                    "decision_spec_sha256": spec_sha,
                    "decision_document_sha256": document_sha,
                    "candidate_fingerprint": fingerprint(record),
                    "draft": draft,
                    "pattern_rule_only": pattern_only,
                },
                review_history=[],
                original_candidate=record,
                reviewed_candidate=updated,
                transformations=transformations,
                unresolved_questions=list(dict.fromkeys(questions)),
            )
        )
    summary = {
        "spec_sha256": spec_sha,
        "decision_document_sha256": document_sha,
        "not_covered": sorted(f"{i}/{t}" for i, t in set(records) - set(by_test)),
    }
    return out, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decisions-output", type=Path, required=True)
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Allow a spec without reviewer/date; outputs are marked draft",
    )
    args = parser.parse_args()
    if args.output.resolve() == args.decisions_output.resolve():
        parser.error("Output paths must be distinct")
    fixtures, summary = apply(args.workspace, args.spec, draft=args.draft)
    payload = {
        "schema_version": "reviewed-evidence-v1",
        "scope": "flag-review decisions applied to model candidates; notes and unresolved "
        "questions retained",
        "draft": args.draft,
        "decision_spec_sha256": summary["spec_sha256"],
        "records": [f.model_dump(mode="json") for f in fixtures],
    }
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    decisions = {
        "schema_version": "reviewed-decisions-v1",
        "fixture_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "draft": args.draft,
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
                "applied_decisions": f.confirming_note["decisions"],
                "pattern_rule_only": f.confirming_note["pattern_rule_only"],
                "supporting_references": f.supporting_references,
                "unresolved_questions": f.unresolved_questions,
            }
            for f in fixtures
        ],
    }
    decision_content = json.dumps(decisions, indent=2, ensure_ascii=False) + "\n"
    for path, text in ((args.output, content), (args.decisions_output, decision_content)):
        if path.exists() and path.read_text(encoding="utf-8") != text:
            parser.error(f"Choose a new output path; existing artifact differs: {path}")
    for path, text in ((args.output, content), (args.decisions_output, decision_content)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    counts: dict[str, int] = {}
    for f in fixtures:
        counts[f.review_action] = counts.get(f.review_action, 0) + 1
    print(f"Applied decisions to {len(fixtures)} records: {counts}")
    if summary["not_covered"]:
        print(f"Not covered by any decision (left unreviewed): {', '.join(summary['not_covered'])}")


if __name__ == "__main__":
    main()
