"""Reviewed-evidence bridge: verification, faithful conversion and record cards.

Synthetic records only, shaped like `review.fixtures` output (reviewed-evidence-v1).
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from combustion_atlas.analysis import evidence_bridge as bridge
from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import DocumentStore
from combustion_atlas.review.fixtures import fingerprint

SHA = "e" * 64


def cell(
    column: str, original: str, value: Any, unit: str | None = None, qualifier: str | None = None
) -> dict[str, Any]:
    return {
        "original_value": original,
        "original_unit": None,
        "provenance": {
            "source_url": "https://psi.nasa.gov/x",
            "file": "bass-ii.csv",
            "row": 3,
            "column": column,
            "page": None,
            "table": None,
            "synthetic": True,
            "source_sha256": SHA,
        },
        "value": value,
        "unit": unit,
        "qualifier": qualifier,
        "uncertainty": None,
    }


def candidate(test_id: str, conditions: dict[str, Any]) -> dict[str, Any]:
    raw = [
        {k: c[k] for k in ("original_value", "original_unit", "provenance")}
        for c in conditions.values()
    ]
    return {
        "identity": {"investigation_id": "PSI-25", "test_id": test_id, "sample_id": None},
        "conditions": conditions,
        "outcomes": [],
        "instrument_settings": {},
        "extra_metadata": {},
        "raw_cells": raw,
        "extraction_confidence": None,
        "validation_status": "review_required",
        "human_review_status": "accepted",
        "issues": [],
    }


def write_pair(
    root: Path, items: list[tuple[dict[str, Any], str, str]], tamper: bool = False
) -> None:
    records, decisions = [], []
    for reviewed, kind, action in items:
        original = {**reviewed, "human_review_status": "unreviewed"}
        ident = reviewed["identity"]
        records.append(
            {
                "investigation_id": ident["investigation_id"],
                "test_id": ident["test_id"],
                "evidence_kind": kind,
                "source_sha256": SHA,
                "candidate_fingerprint": fingerprint(original),
                "review_action": action,
                "supporting_references": ["CSV record 3"],
                "confirming_note": {},
                "review_history": [],
                "original_candidate": original,
                "reviewed_candidate": reviewed,
                "transformations": [],
                "unresolved_questions": ["Is the final O2 reading calibrated?"],
            }
        )
        decisions.append(
            {
                "investigation_id": ident["investigation_id"],
                "test_id": ident["test_id"],
                "candidate_fingerprint": fingerprint(original),
                "source_sha256": SHA,
                "reviewed_fingerprint": fingerprint(reviewed),
                "action": {"accept_extraction": "accept", "needs_research": "needs_research"}[
                    action
                ],
                "unresolved_questions": [],
            }
        )
    content = json.dumps({"schema_version": "reviewed-evidence-v1", "records": records}, indent=2)
    path = root / bridge.EVIDENCE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / bridge.DECISIONS).write_text(
        json.dumps(
            {
                "schema_version": "reviewed-decisions-v1",
                "fixture_sha256": "0" * 64 if tamper else digest,
                "decisions": decisions,
            }
        ),
        encoding="utf-8",
    )


def b1() -> dict[str, Any]:
    return candidate(
        "B1",
        {
            "initial_oxygen": cell("Calibrated initial O2 % by vol", "22.2", 22.2, "%"),
            "thickness_um": cell("Fuel Sample Material", "100 micron PMMA film", 100.0, "um"),
        },
    )


def test_verified_records_become_cards_and_faithful_coverage(tmp_path: Path) -> None:
    approximate = candidate("B2", {"initial_oxygen": cell("O2", "~21.5", 21.5, "%", "approximate")})
    background = candidate("T13", {"initial_oxygen": cell("O2", "21", 21.0, "%")})
    write_pair(
        tmp_path,
        [
            (b1(), "run", "accept_extraction"),
            (approximate, "run", "needs_research"),
            (background, "background_table_row", "accept_extraction"),
        ],
    )
    records, report = bridge.load_reviewed(tmp_path)
    assert report["accepted"] == 3 and report["rejected"] == []

    card = bridge.to_card(records[0])
    assert "Calibrated initial O2 % by vol: 22.2" in card["text"]  # verbatim source cell
    assert "Derived values (interpretations, not source text)" in card["text"]
    assert "Is the final O2 reading calibrated?" in card["text"]
    assert card["physical_page"] == 0 and "CSV record 3" in card["meta"]["locator"]
    assert "background study row" in bridge.to_card(records[2])["text"]

    unconverted: list[dict[str, Any]] = []
    runs = [bridge.to_coverage(r, unconverted) for r in records]
    assert runs[0]["fields"] == {"oxygen_pct": 22.2, "thickness_mm": 0.1}
    assert runs[1]["fields"] == {} and runs[1]["review_action"] == "needs research"
    assert runs[2] is None  # background rows are not flight runs
    assert unconverted == [
        {
            "record": "PSI-25/B2",
            "field": "initial_oxygen",
            "original": "~21.5",
            "reason": "qualifier 'approximate' kept as text",
        }
    ]


def test_tampered_or_changed_evidence_is_rejected(tmp_path: Path) -> None:
    write_pair(tmp_path, [(b1(), "run", "accept_extraction")], tamper=True)
    records, report = bridge.load_reviewed(tmp_path)
    assert records == [] and "evidence file bytes" in report["rejected"][0]["reason"]

    write_pair(tmp_path, [(b1(), "run", "accept_extraction")])
    path = tmp_path / bridge.EVIDENCE
    payload = json.loads(path.read_text())
    payload["records"][0]["reviewed_candidate"]["conditions"]["initial_oxygen"]["value"] = 99.0
    path.write_text(json.dumps(payload, indent=2) + "\n")
    decisions = json.loads((tmp_path / bridge.DECISIONS).read_text())
    decisions["fixture_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / bridge.DECISIONS).write_text(json.dumps(decisions))
    records, report = bridge.load_reviewed(tmp_path)
    assert records == [] and "changed after its decision" in report["rejected"][0]["reason"]

    assert bridge.load_reviewed(tmp_path / "missing")[1]["warnings"]


def test_cards_sync_into_search_without_touching_other_chunks(tmp_path: Path) -> None:
    write_pair(tmp_path, [(b1(), "run", "accept_extraction")])
    records, _ = bridge.load_reviewed(tmp_path)
    page = PageRecord(
        source_id="f" * 16,
        filename="r.pdf",
        sha256="f" * 64,
        physical_page=1,
        text="Oxygen concentration narrative passage.",
    )
    with DocumentStore(tmp_path / "rag.sqlite3") as store:
        store.replace([page], chunk_page(page))
        cards = [bridge.to_card(r) for r in records]
        assert bridge.sync_cards(store, cards)["added_or_changed"] == 1
        assert bridge.sync_cards(store, cards)["added_or_changed"] == 0  # idempotent
        hits = store.search("calibrated initial O2 B1", None, 5)
        card_hit = next(h for h in hits if str(h["chunk_id"]).startswith("card:"))
        assert card_hit["record_card"]["review_action"] == "accepted"
        assert bridge.sync_cards(store, [])["removed"] == 1
        assert store.chunk_count() == 1


def note(kind: str, text: str = "Caveat.", by: str = "reviewer") -> dict[str, Any]:
    return {"kind": kind, "text": text, "by": by, "decision": "D1"}


def test_csv_run_pairs_notes_additional_fields_and_pattern_rows(tmp_path: Path) -> None:
    o12 = candidate(
        "O12",
        {
            "initial_oxygen": cell("Calibrated initial O2 % by vol", "13.6", "13.6", "% by vol"),
            "initial_co": {
                **cell("Initial CO (ppm)", "OR", "OR", "ppm"),
                "notes": [note("unresolved", "OR kept as written.")],
            },
        },
    )
    o12["additional_fields"] = {
        "rod_dimension": {
            **cell("Fuel Sample Material", '3/8" clear rod', "3/8", "in"),
            "notes": [note("unresolved", "Probably the rod diameter.")],
        }
    }
    b11 = candidate(
        "B11",
        {
            "width": {
                **cell("Fuel Sample Material", "2 cm 0.2 mm PMMA film", 2.0, "cm"),
                "notes": [note("assumed", "Width assumed from context.")],
            },
            "thickness": {
                **cell("Fuel Sample Material", "2 cm 0.2 mm PMMA film", "0.2", "mm"),
                "notes": [note("assumed"), note("model", "Parsed.", by="model")],
            },
        },
    )
    t1 = candidate("T1", {"initial_oxygen": cell("O2", "18.5", "18.5", "% by vol")})
    write_pair(tmp_path, [(b1(), "run", "accept_extraction")])  # the v1 pair
    csv_root = tmp_path / "csv"
    write_pair(
        csv_root,
        [
            (o12, "run", "accept_extraction"),
            (b11, "run", "accept_extraction"),
            (t1, "run", "accept_extraction"),
        ],
    )
    for name in ("evidence", "decisions"):  # place as the -csv-run-v1 pair
        source = csv_root / f"data/processed/reviewed-{name}-v1.json"
        source.rename(tmp_path / f"data/processed/reviewed-{name}-csv-run-v1.json")
    path = tmp_path / "data/processed/reviewed-evidence-csv-run-v1.json"
    payload = json.loads(path.read_text())
    payload["records"][2]["confirming_note"] = {"pattern_rule_only": True}
    path.write_text(json.dumps(payload, indent=2) + "\n")
    decisions_path = tmp_path / "data/processed/reviewed-decisions-csv-run-v1.json"
    decisions = json.loads(decisions_path.read_text())
    decisions["fixture_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    decisions_path.write_text(json.dumps(decisions))

    records, report = bridge.load_reviewed(tmp_path)
    assert report["accepted"] == 4 and len(report["files"]) == 2
    cards = {r["candidate"].identity.test_id: bridge.to_card(r) for r in records}
    assert "  note (unresolved, reviewer D1): OR kept as written." in cards["O12"]["text"]
    assert "Additional source content (not mapped to a field):" in cards["O12"]["text"]
    assert "- rod_dimension = 3/8 in" in cards["O12"]["text"]
    assert "not individually reviewed" in cards["T1"]["text"]
    assert cards["T1"]["meta"]["pattern_rule_only"] is True

    unconverted: list[dict[str, Any]] = []
    runs = {r["candidate"].identity.test_id: bridge.to_coverage(r, unconverted) for r in records}
    assert runs["O12"]["fields"] == {"oxygen_pct": 13.6}  # numeric string accepted
    assert runs["B11"]["fields"] == {"thickness_mm": 0.2}  # assumed/model notes allowed
    assert runs["T1"] is None  # pattern-rule-only rows stay out of coverage
    assert "rod_dimension" not in str(runs["O12"])  # additional fields never mapped


def test_draft_pairs_and_duplicate_identities_are_rejected(tmp_path: Path) -> None:
    write_pair(tmp_path, [(b1(), "run", "accept_extraction")])
    path = tmp_path / bridge.EVIDENCE
    payload = json.loads(path.read_text())
    copy = tmp_path / "data/processed/reviewed-evidence-copy.json"
    copy.write_text(path.read_text())
    (tmp_path / "data/processed/reviewed-decisions-copy.json").write_text(
        (tmp_path / bridge.DECISIONS).read_text()
    )
    records, report = bridge.load_reviewed(tmp_path)
    assert records == [] and "more than one file" in report["rejected"][0]["reason"]

    payload["draft"] = True
    copy.unlink()
    path.write_text(json.dumps(payload, indent=2) + "\n")
    decisions = json.loads((tmp_path / bridge.DECISIONS).read_text())
    decisions["fixture_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / bridge.DECISIONS).write_text(json.dumps(decisions))
    records, report = bridge.load_reviewed(tmp_path)
    assert records == [] and any("draft" in r["reason"] for r in report["rejected"])


def test_named_test_ids_pin_their_record_card(tmp_path: Path) -> None:
    from combustion_atlas.rag.search import retrieve

    write_pair(tmp_path, [(b1(), "run", "accept_extraction")])
    records, _ = bridge.load_reviewed(tmp_path)
    pages = [
        PageRecord(
            source_id="f" * 16,
            filename="r.pdf",
            sha256="f" * 64,
            physical_page=i,
            text="Initial oxygen readings were calibrated for every test in the series.",
        )
        for i in range(1, 8)
    ]
    with DocumentStore(tmp_path / "rag.sqlite3") as store:
        store.replace(pages, [c for p in pages for c in chunk_page(p)])
        bridge.sync_cards(store, [bridge.to_card(r) for r in records])
        assert store.cards_for_identifiers("What was the initial oxygen for test B1?")
        assert store.cards_for_identifiers("Tests at 22.2 percent oxygen") == []  # numbers only
        hits = retrieve(store, "initial oxygen readings test B1", method="keyword", top_k=3)
        assert str(hits[0]["chunk_id"]).startswith("card:PSI-25:B1:")
        assert hits[0]["record_card"]["review_action"] == "accepted"
