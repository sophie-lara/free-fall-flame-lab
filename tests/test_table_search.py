"""Table cards, exact-value row matching, search pinning and the proposed-tests layer.

Synthetic, FLEX-shaped records only.
"""

from pathlib import Path
from typing import Any

from combustion_atlas.analysis import table_index
from combustion_atlas.analysis.evidence_bridge import sync_cards, to_proposed
from combustion_atlas.rag.row_match import match_rows
from combustion_atlas.rag.search import retrieve
from combustion_atlas.rag.store import DocumentStore
from combustion_atlas.review.evidence_schema import EvidenceCandidate

SHA = "f" * 64


def value(column: str, v: Any, unit: str | None = None, row: int = 3, notes=()) -> dict:
    return {
        "original_value": str(v),
        "original_unit": None,
        "provenance": {
            "source_url": "https://psi.nasa.gov/x",
            "file": "eird.pdf",
            "row": row,
            "column": column,
            "page": 48,
            "table": "8",
            "synthetic": True,
            "source_sha256": SHA,
        },
        "value": v,
        "unit": unit,
        "qualifier": None,
        "uncertainty": None,
        "notes": list(notes),
    }


AMBIGUOUS = {
    "kind": "ambiguous",
    "text": "D0 = 3, 5 mm not assigned",
    "by": "pipeline",
    "decision": None,
}


def record(
    test: str, pressure: float, oxygen: float, co2: float, row: int, suppressant: str = "CO2"
) -> dict[str, Any]:
    conditions = {
        "pressure": value("P (atm)", pressure, "atm", row),
        "oxygen_mole_fraction": value("XO2", oxygen, None, row),
        "suppressant_mole_fraction": value("XCO2", co2, None, row),
        "suppressant": value("condition row", suppressant, None, 1),
        "droplet_diameter": value("condition row", "3, 5", "mm", 1, [AMBIGUOUS]),
    }
    candidate = EvidenceCandidate.model_validate(
        {
            "identity": {"investigation_id": "PSI-69", "test_id": test, "sample_id": None},
            "conditions": conditions,
            "outcomes": [],
            "instrument_settings": {},
            "extra_metadata": {},
            "additional_fields": {},
            "raw_cells": [
                {k: c[k] for k in ("original_value", "original_unit", "provenance")}
                for c in conditions.values()
            ],
            "extraction_confidence": None,
            "validation_status": "review_required",
            "human_review_status": "accepted",
            "issues": [
                {
                    "code": "source_table",
                    "field": "Record",
                    "message": "EIRD Table 8: CO2 matrix.",
                    "severity": "review",
                },
                {
                    "code": "evidence_class",
                    "field": "Record",
                    "severity": "review",
                    "message": "Planned test condition from a test matrix; not an observed result.",
                },
            ],
        }
    )
    return {
        "candidate": candidate,
        "evidence": {"evidence_kind": "planned_test_condition", "unresolved_questions": []},
        "decision": {},
        "review_action": "accepted",
        "pattern_rule_only": False,
    }


RECORDS = [
    record("FLEX-T8-61", 0.85, 0.25, 0.50, 13),
    record("FLEX-T8-62", 0.85, 0.25, 0.70, 14),
    record("FLEX-T8-70", 1.00, 0.10, 0.70, 22),
]


def rows() -> list[dict[str, Any]]:
    return table_index.build(RECORDS)[1]


def ids(matches) -> list[str]:
    return [m["test_id"] for m in matches]


def test_one_card_per_table_with_ranges_caveats_and_notes() -> None:
    cards, payloads = table_index.build(RECORDS)
    assert len(cards) == 1 and len(payloads) == 3
    text = cards[0]["text"]
    assert text.startswith("Table — EIRD Table 8: CO2 matrix.")
    assert "pressure 0.85–1 atm" in text and "Tests proposed by" in text
    assert "ambiguous (3 of 3 rows)" in text and "not run as listed" in text
    # Review bookkeeping and reviewer names never reach what readers see.
    assert "Review:" not in text and "not an observed result" not in text
    row = payloads[0]
    assert row["provenance"].startswith("A test proposed by")
    assert row["caveats"] == [] and "Review:" not in row["text"]
    duplicated = [*RECORDS]  # a note on two values of one row still counts as one row
    assert all(n["rows"] <= len(duplicated) for n in cards[0]["meta"]["notes"])
    assert payloads[0]["card_id"] == cards[0]["card_id"]


def test_rows_need_two_exact_numbers_and_all_must_match() -> None:
    assert ids(match_rows("CO2 at 0.85 atm with 0.25 oxygen and 0.50", rows())) == ["FLEX-T8-61"]
    assert ids(match_rows("0.85 atm", rows())) == []  # one number: table card only
    assert ids(match_rows("0.85 atm 0.25 oxygen 0.33", rows())) == []  # partial: nothing
    assert ids(match_rows("0.850 atm 0.250 oxygen", rows())) == ["FLEX-T8-61", "FLEX-T8-62"]


def test_hint_words_choose_columns_and_percent_converts_with_a_note() -> None:
    assert ids(match_rows("0.70 oxygen 1.00 atm", rows())) == []  # 0.70 is not an O2 value
    found = match_rows("10% oxygen 1.00 atm", rows())
    assert ids(found) == ["FLEX-T8-70"]
    assert "matched as mole fraction" in found[0]["match"][0]["conversion"]


def test_species_named_in_question_filter_rows() -> None:
    helium = [*RECORDS, record("FLEX-T9-150", 0.85, 0.25, 0.50, 40, suppressant="He")]
    built = table_index.build(helium)[1]
    assert ids(match_rows("He 0.85 atm 0.25 oxygen 0.50", built)) == ["FLEX-T9-150"]
    assert ids(match_rows("CO2 0.85 atm 0.25 oxygen 0.50", built)) == ["FLEX-T8-61"]


def test_search_pins_matched_rows_above_table_cards(tmp_path: Path) -> None:
    cards, payloads = table_index.build(RECORDS)
    with DocumentStore(tmp_path / "rag.sqlite3") as store:
        sync_cards(store, cards)
        table_index.sync_rows(store, payloads)
        broad = retrieve(store, "CO2 matrix")
        assert [r["record_card"]["kind"] for r in broad] == ["table"]
        exact = retrieve(store, "CO2 matrix at 0.85 atm 0.25 oxygen 0.50")
        assert exact[0]["record_card"]["kind"] == "row"
        assert exact[0]["record_card"]["test_id"] == "FLEX-T8-61"
        assert exact[0]["record_card"]["values"][0]["unit"] == "atm"
        assert exact[0]["record_card"]["provenance"].startswith("A test proposed by")
        named = retrieve(store, "show FLEX-T8-70")
        assert named[0]["record_card"]["test_id"] == "FLEX-T8-70"


def test_proposed_layer_converts_and_omits_ambiguous_values() -> None:
    point = to_proposed(RECORDS[0])
    assert point is not None
    assert point["fields"] == {"pressure_kpa": 86.126, "oxygen_pct": 25.0}
    assert "pressure 0.85 atm → 86.126 kPa" in point["conversions"]
    assert any("droplet_diameter" in o for o in point["omitted"])
    assert any("not an observed result" in c for c in point["caveats"])
    assert point["document_id"] and len(point["document_id"]) == 16
    assert point["source_url"] == RECORDS[0]["candidate"].raw_cells[0].provenance.source_url
