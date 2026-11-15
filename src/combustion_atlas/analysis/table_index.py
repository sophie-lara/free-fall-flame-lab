"""One search card per source table, plus a structured row index for exact-value lookup.

Broad searches should find a table, not flood results with its rows. Each source table
(a CSV experiment table, or one table of a PDF) becomes a single card: title, evidence
type, review summary, value ranges, constant conditions, table-level caveats, the
distinct value notes, and a source locator. Individual rows are kept out of the text
index and stored structurally (values, units, original text, notes, locator) so the
row matcher can return exact rows when a question names two or more of their values.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any

from combustion_atlas.review.evidence_schema import EvidenceCandidate
from combustion_atlas.review.fixtures import fingerprint

EVIDENCE_LABELS = {
    "run": "experiment runs (observed results)",
    "background_table_row": "background data (literature or calculated values, not runs)",
    "planned_test_condition": "proposed test conditions (planned, not observed results)",
}
# Per-row bookkeeping that does not belong on a table card.
ROW_ONLY_ISSUES = {
    "human_review_required",
    "review_decisions",
    "mapping_validation",
    "model_note",
    "multiple_source_cells",
    "unreferenced_source_cell",
    "source_table",
}
# Review bookkeeping stays in the reviewed-evidence files; it is not shown to readers.
HIDDEN_ISSUES = ROW_ONLY_ISSUES | {
    "evidence_class",
    "preliminary_test_matrix",
    "extraction_spot_checked",
}
HIDDEN_QUESTION_WORDS = ("spot-checked", "review", "pattern rule")
# Who produced a source document, for the plain-language provenance line.
SOURCE_DOCUMENTS = {
    "be236c283ffd597bb79a4715fd4b24d296b2b93de1144c676c119b52a3a3ebe9": {
        "document": "NASA's FLEX Research Requirements Document (Droplet Flame "
        "Extinguishment in Microgravity)",
        "authors": "the FLEX research team (lead: Forman A. Williams, UC San Diego)",
    },
}


def _pages_text(pages: list[int]) -> str:
    if not pages:
        return ""
    if len(pages) == 1:
        return f"page {pages[0]}"
    return f"pages {pages[0]}–{pages[-1]}"


def provenance(kind: str | None, sha256: str, title: str, pages: list[int], plural: bool) -> str:
    """One plain sentence saying where table data comes from and what it is."""
    doc = SOURCE_DOCUMENTS.get(sha256, {})
    document = doc.get("document", "the source document")
    authors = doc.get("authors", "the investigators")
    table = re.sub(r"^EIRD\s+", "", title).rstrip(".")
    where = f"{document}, {table}" + (f" ({_pages_text(pages)})" if pages else "")
    if kind == "planned_test_condition":
        lead = "Tests proposed" if plural else "A test proposed"
        return (
            f"{lead} by {authors} in {where}. Planned conditions only: not run as listed, "
            "and no results are recorded."
        )
    if kind == "background_table_row":
        return f"Background data from {where}: literature or calculated values, not a FLEX run."
    return ""


def display_caveats(candidate: EvidenceCandidate) -> list[str]:
    return [i.message for i in candidate.issues if i.code not in HIDDEN_ISSUES]


CAVEAT_NOTES = ("ambiguous", "unresolved", "pending", "assumed", "inferred", "definition")
MAX_CARD_NOTES = 12


def _values(candidate: EvidenceCandidate) -> list[tuple[str, str, Any, str]]:
    """(group, field, EvidenceValue, column label) for every interpreted value."""
    out = [("condition", name, v, v.provenance.column) for name, v in candidate.conditions.items()]
    out += [("outcome", o.outcome_type, o, o.provenance.column) for o in candidate.outcomes]
    out += [
        ("additional", name, v, v.provenance.column)
        for name, v in candidate.additional_fields.items()
    ]
    return out


def table_key(record: dict[str, Any]) -> str:
    candidate: EvidenceCandidate = record["candidate"]
    first = candidate.raw_cells[0].provenance
    return f"{first.source_sha256[:16]}:{first.table or 'csv'}"


def table_title(records: list[dict[str, Any]]) -> str:
    candidate: EvidenceCandidate = records[0]["candidate"]
    for issue in candidate.issues:
        if issue.code == "source_table":
            return issue.message
    first = candidate.raw_cells[0].provenance
    name = re.sub(r"\.(csv|pdf)$", "", first.file, flags=re.I)
    name = re.sub(r"^PSI-\d+_", "", name).replace("_", " ")
    if first.table:
        return f"{name}, Table {first.table}"
    return f"{name} (CSV)"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", value.strip()):
        return float(value.strip())
    return None


def _fmt(number: float) -> str:
    return f"{number:g}"


def row_payload(record: dict[str, Any], card_id: str, title: str) -> dict[str, Any]:
    candidate: EvidenceCandidate = record["candidate"]
    item = record["evidence"]
    identity = candidate.identity
    first = candidate.raw_cells[0].provenance
    values = []
    for group, field, value, label in _values(candidate):
        values.append(
            {
                "group": group,
                "field": field,
                "label": label,
                "value": value.value,
                "unit": value.unit,
                "original": value.original_value,
                "page": value.provenance.page,
                "notes": [n.model_dump(mode="json") for n in value.notes],
            }
        )
    pages = sorted({v["page"] for v in values if v["page"]})
    origin = provenance(item.get("evidence_kind"), first.source_sha256, title, pages, False)
    caveats = display_caveats(candidate)
    questions = [
        q
        for q in item.get("unresolved_questions") or []
        if not any(w in q.lower() for w in HIDDEN_QUESTION_WORDS)
    ]
    lines = [
        f"Table row — {title}: {identity.investigation_id} {identity.test_id}",
        origin
        or f"Evidence: {EVIDENCE_LABELS.get(item.get('evidence_kind') or '', 'table data')}.",
    ]
    for v in values:
        unit = f" {v['unit']}" if v["unit"] else ""
        lines.append(f"- {v['field']} = {v['value']}{unit}  [source: {v['original']}]")
        lines += [f"  note ({n['kind']}): {n['text']}" for n in v["notes"] if n["kind"] != "model"]
    lines += [f"Caveat: {c}" for c in caveats]
    where = (
        f"{first.file}, PDF page {', '.join(map(str, pages))}, table {first.table}, row {first.row}"
        if first.page
        else f"{first.file}, CSV record {first.row}"
    )
    lines.append(f"Source: {where}")
    return {
        "row_id": f"row:{identity.investigation_id}:{identity.test_id}",
        "card_id": card_id,
        "table_title": title,
        "investigation_id": identity.investigation_id,
        "test_id": identity.test_id,
        "evidence_kind": item.get("evidence_kind"),
        "review_action": record["review_action"],
        "pattern_rule_only": bool(record.get("pattern_rule_only")),
        "source": {
            "file": first.file,
            "source_url": first.source_url,
            "source_sha256": first.source_sha256,
            "page": pages[0] if pages else None,
            "table": first.table,
            "row": first.row,
        },
        "locator": where,
        "provenance": origin,
        "values": values,
        "caveats": caveats,
        "open_questions": questions,
        "text": "\n".join(lines),
    }


def build(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Table cards (for the text index) and row payloads (for exact lookup)."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[table_key(record)].append(record)
    cards, rows = [], []
    for key, members in sorted(groups.items()):
        title = table_title(members)
        card = _card(key, title, members)
        cards.append(card)
        rows += [row_payload(r, card["card_id"], title) for r in members]
    return cards, rows


def _card(key: str, title: str, members: list[dict[str, Any]]) -> dict[str, Any]:
    first_candidate: EvidenceCandidate = members[0]["candidate"]
    first = first_candidate.raw_cells[0].provenance
    kinds = Counter(m["evidence"].get("evidence_kind") for m in members)
    reviews = Counter(m["review_action"] for m in members)
    numeric: dict[str, list[float]] = defaultdict(list)
    units: dict[str, Counter[str]] = defaultdict(Counter)
    texts: dict[str, Counter[str]] = defaultdict(Counter)
    notes: Counter[tuple[str, str]] = Counter()
    caveats: Counter[str] = Counter()
    pages: set[int] = set()
    for m in members:
        candidate: EvidenceCandidate = m["candidate"]
        row_notes: set[tuple[str, str]] = set()  # counted once per row
        for _, field, value, _ in _values(candidate):
            number = _number(value.value)
            if number is not None:
                numeric[field].append(number)
                if value.unit:
                    units[field][value.unit] += 1
            elif value.value not in (None, ""):
                texts[field][str(value.value)] += 1
            if value.provenance.page:
                pages.add(value.provenance.page)
            for note in value.notes:
                if note.kind in CAVEAT_NOTES:
                    row_notes.add((note.kind, note.text))
        notes.update(row_notes)
        for message in display_caveats(candidate):
            caveats[message] += 1
    ids = [m["candidate"].identity.test_id for m in members]
    origin = provenance(
        next(iter(kinds)) if len(kinds) == 1 else None,
        first.source_sha256,
        title,
        sorted(pages),
        len(members) > 1,
    )
    lines = [
        f"Table — {title} ({first_candidate.identity.investigation_id})",
        origin
        or "Evidence: "
        + "; ".join(f"{EVIDENCE_LABELS.get(k or '', k)} ({n})" for k, n in kinds.items())
        + ".",
        f"{len(members)} rows: {ids[0]} … {ids[-1]}" if len(ids) > 1 else f"1 row: {ids[0]}",
    ]
    ranges = []
    for field, found in sorted(numeric.items()):
        unit = units[field].most_common(1)[0][0] if units[field] else ""
        low, high = min(found), max(found)
        span = _fmt(low) if low == high else f"{_fmt(low)}–{_fmt(high)}"
        ranges.append(f"{field} {span} {unit}".rstrip())
    if ranges:
        lines.append("Value ranges: " + "; ".join(ranges) + ".")
    constants = []
    for field, labels in sorted(texts.items()):
        distinct = list(labels)
        if len(distinct) <= 4:
            constants.append(f"{field}: {' | '.join(distinct)}")
    if constants:
        lines.append("Conditions and labels: " + "; ".join(constants) + ".")
    if caveats:
        lines += ["Caveats:", *[f"- {c}" for c, _ in caveats.most_common()]]
    if notes:
        lines.append("Notes on values:")
        for (kind, text), count in notes.most_common(MAX_CARD_NOTES):
            lines.append(f"- {kind} ({count} of {len(members)} rows): {text}")
        if len(notes) > MAX_CARD_NOTES:
            lines.append(f"- … and {len(notes) - MAX_CARD_NOTES} more distinct notes")
    if first.page:
        page_text = ", ".join(map(str, sorted(pages))) or str(first.page)
        locator = f"{first.file}, PDF page {page_text}, table {first.table}"
    else:
        locator = f"{first.file} (CSV experiment table)"
    lines.append(f"Source: {locator}")
    lines.append(
        "Individual rows appear when a question gives two or more of a row's exact values."
    )
    text = "\n".join(lines)
    card_fp = fingerprint({"text": text, "rows": sorted(ids)})
    return {
        "card_id": f"card:table:{key}:{card_fp[:12]}",
        "fingerprint": card_fp,
        "source_id": first.source_sha256[:16],
        "source_sha256": first.source_sha256,
        "filename": first.file,
        "source_url": first.source_url,
        "investigation_id": first_candidate.identity.investigation_id,
        "physical_page": min(pages) if pages else 0,
        "text": text,
        "meta": {
            "kind": "table",
            "table_title": title,
            "investigation_id": first_candidate.identity.investigation_id,
            "evidence_kinds": dict(kinds),
            "review_action": ", ".join(f"{k} ({n})" for k, n in reviews.items()),
            "rows": len(members),
            "pages": sorted(pages),
            "table": first.table,
            "locator": locator,
            "provenance": origin,
            "caveats": [c for c, _ in caveats.most_common()],
            "notes": [{"kind": k, "text": t, "rows": n} for (k, t), n in notes.most_common()],
        },
    }


def sync_rows(store: Any, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Replace the structured row index with `rows` (not part of the text index)."""
    connection = store.connection
    with connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS record_rows ("
            "row_id TEXT PRIMARY KEY, card_id TEXT NOT NULL, investigation_id TEXT, "
            "test_id TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        connection.execute("DELETE FROM record_rows")
        connection.executemany(
            "INSERT INTO record_rows VALUES (?, ?, ?, ?, ?)",
            [
                (
                    r["row_id"],
                    r["card_id"],
                    r["investigation_id"],
                    r["test_id"],
                    json.dumps(r, ensure_ascii=False),
                )
                for r in rows
            ],
        )
    return {"rows": len(rows)}
