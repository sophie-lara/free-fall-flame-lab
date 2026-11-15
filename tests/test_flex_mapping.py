"""FLEX test-matrix mapping: validation rules and deterministic per-test expansion.

Synthetic, Table-8-shaped data only; no provider calls.
"""

import hashlib
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from combustion_atlas.ingestion import flex_mapping as m
from combustion_atlas.ingestion import flex_pdf_run as f

CONDITIONS = "Fuel: C7H16, Diluent: N2, Flow: 0.0 cm/s, D0 = 3, 5 mm, XN2 = 1.0 − XO2."


def cell(row, column, text, role="data", span=1, page=48):
    return f.ExtractedCell(
        page=page,
        row=row,
        column=column,
        row_span=1,
        column_span=span,
        role=role,
        text=text,
        state="present",
        uncertainty=None,
    )


def extraction():
    cells = [
        cell(0, 0, CONDITIONS, role="row_header", span=3),
        cell(1, 0, "Test No.", role="header"),
        cell(1, 1, "P (atm)", role="header"),
        cell(1, 2, "XO2", role="header"),
        cell(2, 0, "51"),
        cell(2, 1, "0.70"),
        cell(2, 2, "0.25"),
        cell(3, 0, "Fuel: CH3OH.", role="row_header", span=3),
        cell(4, 0, "79", page=49),
        cell(4, 1, "0.70", page=49),
        cell(4, 2, "0.30", page=49),
    ]
    return f.TableExtraction(
        label="8",
        caption="Table 8: CO2 suppressant efficacy test matrix.",
        header_notes=[],
        rows=5,
        columns=3,
        cells=cells,
        footnotes=[],
        context_flags=[],
        uncertainties=[],
    )


def cond(field, text, value, unit=None, status="single"):
    return m.ConditionValue(
        canonical_field=field, source_text=text, value=value, unit=unit, status=status, note=None
    )


def mapping(**overrides):
    base = dict(
        evidence_class="planned_test_matrix",
        evidence_class_quote="test matrix",
        evidence_class_reason="A test matrix lists planned conditions.",
        column_mappings=[
            m.ColumnMapping(
                column=0,
                header_text="Test No.",
                canonical_field="test_number",
                unit=None,
                quantity_kind="identifier",
                note=None,
            ),
            m.ColumnMapping(
                column=1,
                header_text="P (atm)",
                canonical_field="pressure",
                unit="atm",
                quantity_kind="planned_condition",
                note=None,
            ),
            m.ColumnMapping(
                column=2,
                header_text="XO2",
                canonical_field="oxygen_mole_fraction",
                unit=None,
                quantity_kind="planned_condition",
                note=None,
            ),
        ],
        condition_rows=[
            m.ConditionRow(
                source_row=0,
                conditions=[
                    cond("fuel", "Fuel: C7H16", "C7H16"),
                    cond("diluent", "Diluent: N2", "N2"),
                    cond("flow_velocity", "Flow: 0.0 cm/s", "0.0 cm/s", "cm/s"),
                    cond(
                        "droplet_diameter",
                        "D0 = 3, 5 mm",
                        "3, 5 mm",
                        "mm",
                        status="multiple_values_unassigned",
                    ),
                    cond("diluent_mole_fraction", "XN2 = 1.0 − XO2", "1.0 − XO2", status="formula"),
                ],
            ),
            m.ConditionRow(source_row=3, conditions=[cond("fuel", "Fuel: CH3OH", "CH3OH")]),
        ],
        context_flags=[],
        notes=[],
    )
    base.update(overrides)
    return m.TableMapping(**base)


def by_id(records):
    return {r["identity"]["test_id"]: r for r in records}


def test_expansion_copies_cells_and_applies_condition_rows_in_order() -> None:
    records = by_id(m.expand(mapping(), extraction()))
    assert set(records) == {"FLEX-T8-51", "FLEX-T8-79"}
    first, later = records["FLEX-T8-51"], records["FLEX-T8-79"]
    assert first["conditions"]["pressure"]["value"] == 0.70
    assert first["conditions"]["pressure"]["provenance"]["page"] == 48
    assert later["conditions"]["oxygen_mole_fraction"]["provenance"]["page"] == 49
    assert first["conditions"]["fuel"]["value"] == "C7H16"
    assert later["conditions"]["fuel"]["value"] == "CH3OH"  # overridden by the fuel row
    assert later["conditions"]["diluent"]["value"] == "N2"  # carried from the first row
    assert first["conditions"]["flow_velocity"]["value"] == 0.0  # unit not repeated
    assert first["conditions"]["droplet_diameter"]["value"] == "3, 5"
    assert first["conditions"]["flow_velocity"]["original_value"] == "Flow: 0.0 cm/s"
    assert "planned test condition" in first["issues"][0]["message"].lower()


def test_unassigned_values_get_ambiguous_note_even_if_model_says_single() -> None:
    lax = mapping()
    lax.condition_rows[0].conditions[3].status = "single"
    record = m.expand(lax, extraction())[0]
    notes = record["conditions"]["droplet_diameter"]["notes"]
    assert [n["kind"] for n in notes] == ["ambiguous"]
    assert "without saying which value applies" in notes[0]["text"]
    assert "multiple_values_not_flagged" in " ".join(m.validate(lax, extraction(), "test matrix"))


def test_formula_is_kept_as_additional_field_not_computed() -> None:
    record = m.expand(mapping(), extraction())[0]
    assert "diluent_mole_fraction" not in record["conditions"]
    extra = record["additional_fields"]["condition_XN2"]
    assert extra["value"] == "1.0 − XO2"
    assert "not computed" in extra["notes"][0]["text"]


def test_validation_flags_non_verbatim_unmapped_and_missing_rows() -> None:
    bad = mapping(
        column_mappings=mapping().column_mappings[:2],
        condition_rows=[
            m.ConditionRow(source_row=0, conditions=[cond("fuel", "Fuel: hexane", "x")])
        ],
        evidence_class_quote="observed results",
    )
    issues = " ".join(m.validate(bad, extraction(), "Table 8 test matrix"))
    for code in (
        "column_2:not_mapped",
        "source_text_not_verbatim",
        "row_3:condition_row_not_mapped",
        "evidence_class_quote_not_verbatim",
    ):
        assert code in issues
    assert m.validate(mapping(), extraction(), "a test matrix") == []


def test_plan_requires_recorded_extraction_review(tmp_path) -> None:
    with pytest.raises(ValueError, match="extraction review"):
        m.create_plan(tmp_path, [{"extraction": "x", "extraction_sha256": "0"}], Decimal("1"))


def test_live_run_writes_mapping_candidates_and_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(m, "check_source", lambda root: tmp_path / "eird.pdf")
    monkeypatch.setattr(m, "environment", lambda root: {"code": "fixed"})
    result = {
        "contract": "flex-table-extraction-v1",
        "source": {"sha256": f.SOURCE["sha256"]},
        "target": {"label": "8", "table_pages": [48, 49], "evidence_class": "planned_test_matrix"},
        "extraction": extraction().model_copy(update={"label": "Table 8"}).model_dump(mode="json"),
    }
    path = tmp_path / "extraction.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    entry = {
        "extraction": "extraction.json",
        "extraction_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "extraction_reviewer": "Reviewer",
        "extraction_reviewed_at": "2026-11-14",
    }
    loader = lambda p, ns: {n: {"text": "Table 8 test matrix", "png": b""} for n in ns}  # noqa: E731
    plan = m.create_plan(tmp_path, [entry], Decimal("1"), loader)
    assert plan["targets"][0]["context_pages"] == [47, 48, 49, 50]

    class Responses:
        def parse(self, **kwargs):
            usage = SimpleNamespace(
                model_dump=lambda mode: {"input_tokens": 100, "output_tokens": 100}
            )
            return SimpleNamespace(output_parsed=mapping(), usage=usage, id="r", model="x")

    out = tmp_path / "data/processed/full-runs/map"
    m.execute(
        tmp_path,
        plan,
        out,
        allow_calls=True,
        client=SimpleNamespace(responses=Responses()),
        loader=loader,
    )
    saved = json.loads((out / "table-08/candidates.json").read_text(encoding="utf-8"))
    assert len(saved["records"]) == 2 and saved["status"] == "unreviewed"
    assert saved["records"][0]["identity"]["test_id"] == "FLEX-T8-51"  # planned label wins
    assert (out / "table-08/review.md").exists() and not (out / ".run-lock").exists()


def test_annotate_adds_reviewer_notes_and_requires_checked_tables(tmp_path) -> None:
    folder = tmp_path / "run/table-08"
    folder.mkdir(parents=True)
    mapping_file = folder / "mapping.json"
    mapping_file.write_text(json.dumps({"target": {"label": "8"}}), encoding="utf-8")
    records = m.expand(mapping(), extraction())
    (folder / "candidates.json").write_text(
        json.dumps(
            {
                "mapping_sha256": hashlib.sha256(mapping_file.read_bytes()).hexdigest(),
                "records": records,
            }
        ),
        encoding="utf-8",
    )
    review = {
        "schema_version": "flex-table-review-v1",
        "source_sha256": f.SOURCE["sha256"],
        "tables": {"8": {"status": "spot_checked"}},
        "record_notes": [
            {
                "id": "N1",
                "tables": ["8"],
                "code": "preliminary_test_matrix",
                "message": "Not the final test matrix.",
                "decided_by": "Reviewer",
            }
        ],
    }
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    combined = m.annotate(tmp_path, review_path, [folder.relative_to(tmp_path) / "candidates.json"])
    codes = [i["code"] for i in combined["records"][0]["issues"]]
    assert "preliminary_test_matrix" in codes and "extraction_spot_checked" in codes
    assert len(combined["records"]) == 2 and combined["status"] == "unreviewed"

    review["tables"]["8"]["status"] = "pending"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(ValueError, match="no recorded check"):
        m.annotate(tmp_path, review_path, [folder.relative_to(tmp_path) / "candidates.json"])
