import copy

import pytest
from pydantic import ValidationError

from combustion_atlas.review.evidence_schema import EvidenceCandidate, ValueNote
from combustion_atlas.review.flag_decisions import (
    Context,
    load_spec,
    model_notes,
    rule_d1,
    rule_d2,
    rule_d3,
    rule_d4,
    rule_d6,
    rule_d7,
    rule_d8,
)

SHA = "a" * 64


def cell(column: str, text: str) -> dict:
    return {
        "original_value": text,
        "original_unit": None,
        "provenance": {
            "source_url": "https://example.test/synthetic",
            "file": "synthetic.csv",
            "row": 2,
            "column": column,
            "page": None,
            "table": None,
            "synthetic": True,
            "source_sha256": SHA,
        },
    }


def value(column: str, text: str, v, unit=None, note=None) -> dict:
    return {**cell(column, text), "value": v, "unit": unit, "qualifier": None, "uncertainty": note}


def candidate(material_text: str, conditions: dict, metadata: dict | None = None) -> dict:
    return {
        "identity": {"investigation_id": "PSI-25", "test_id": "X1", "sample_id": None},
        "conditions": {
            "material_description": value("Fuel Sample Material", material_text, material_text),
            **conditions,
        },
        "outcomes": [],
        "instrument_settings": {},
        "extra_metadata": metadata or {},
        "raw_cells": [cell("Fuel Sample Material", material_text)],
        "extraction_confidence": None,
        "validation_status": "review_required",
        "human_review_status": "unreviewed",
        "issues": [],
    }


def kinds(v: dict) -> list[str]:
    return [n["kind"] for n in v.get("notes", [])]


def test_d1_accepts_unlabeled_dimensions_with_assumed_note() -> None:
    text = "2 cm   0.2 mm PMMA film"
    c = candidate(
        text,
        {
            "width": value("Fuel Sample Material", text, "2 cm", "cm"),
            "thickness": value("Fuel Sample Material", text, 0.2, "mm"),
        },
    )
    rule_d1(Context(c, "D1"))
    assert c["conditions"]["width"]["value"] == 2.0  # duplicated unit stripped
    assert kinds(c["conditions"]["width"]) == ["assumed"]
    assert kinds(c["conditions"]["thickness"]) == ["assumed"]
    EvidenceCandidate.model_validate(c)


def test_d2_never_forces_single_dimension_into_thickness() -> None:
    text = "2 cm SIBAL"
    c = candidate(
        text,
        {
            "material": value("Fuel Sample Material", text, "SIBAL"),
            "thickness": value("Fuel Sample Material", text, 2.0, "cm"),
        },
        {"unmapped_5": cell("Fuel Sample Material", text)},
    )
    ctx = Context(c, "D2")
    rule_d2(ctx)
    assert "thickness" not in c["conditions"]
    assert "unmapped_5" not in c["extra_metadata"]
    extra = c["additional_fields"]["unlabeled_dimension"]
    assert (extra["value"], extra["unit"]) == (2.0, "cm")
    assert kinds(extra) == ["unresolved"]
    assert "unclear" in extra["notes"][0]["text"]
    assert ctx.questions
    EvidenceCandidate.model_validate(c)


def test_d3_keeps_named_material_but_does_not_infer_pmma() -> None:
    named = candidate(
        '1/2" clear PMMA rod',
        {
            "material": value("Fuel Sample Material", '1/2" clear PMMA rod', "PMMA"),
            "width": value("Fuel Sample Material", '1/2" clear PMMA rod', "1/2", "in"),
        },
    )
    rule_d3(Context(named, "D3"))
    assert named["conditions"]["material"]["value"] == "PMMA"
    assert "width" not in named["conditions"]
    assert named["additional_fields"]["rod_dimension"]["value"] == "1/2"

    unnamed = candidate(
        "1/4 clear rod",
        {"material": value("Fuel Sample Material", "1/4 clear rod", "PMMA")},
    )
    rule_d3(Context(unnamed, "D3"))
    assert "material" not in unnamed["conditions"]
    assert kinds(unnamed["conditions"]["material_description"]) == ["unresolved"]
    rod = unnamed["additional_fields"]["rod_dimension"]
    assert rod["unit"] is None and "not stated" in rod["notes"][0]["text"]
    EvidenceCandidate.model_validate(unnamed)


def test_d4_applies_width_context_and_typo_note() -> None:
    text = "4 mm thick   2 cm 2ide PMMA slab"
    c = candidate(text, {"thickness": value("Fuel Sample Material", text, 4.0, "mm")})
    rule_d4(Context(c, "D4"))
    width = c["conditions"]["width"]
    assert (width["value"], width["unit"]) == (2.0, "cm")
    assert "typo" in width["notes"][0]["text"]
    assert kinds(c["conditions"]["thickness"]) == []  # labeled: no assumption note


def test_d6_keeps_marker_and_explains_likely_meaning() -> None:
    c = candidate("x", {"initial_co": value("Initial CO (ppm)", "OR", "OR", "ppm")})
    rule_d6(Context(c, "D6"))
    co = c["conditions"]["initial_co"]
    assert co["value"] == "OR"
    assert kinds(co) == ["unresolved"] and "out of range" in co["notes"][0]["text"]


def test_d7_records_inference_without_changing_value_and_pends_figure() -> None:
    c = candidate("x", {"thickness": value("Samle Thickness ", "037 mm", "037", "mm")})
    rule_d7(Context(c, "D7"))
    assert c["conditions"]["thickness"]["value"] == "037"
    assert kinds(c["conditions"]["thickness"]) == ["inferred"]
    fig = candidate("x", {"thickness": value("Samle Thickness ", "See Fig. 5", None)})
    ctx = Context(fig, "D7")
    rule_d7(ctx)
    assert kinds(fig["conditions"]["thickness"]) == ["pending"] and ctx.questions


def test_model_notes_surface_once() -> None:
    c = candidate("x", {"width": value("Fuel Sample Material", "x", 2.0, "cm", note="Parsed")})
    model_notes(c)
    model_notes(c)
    assert [n["by"] for n in c["conditions"]["width"]["notes"]] == ["model"]


def test_schema_is_backward_compatible_and_rejects_unknown_note_kinds() -> None:
    old = candidate("x", {})
    EvidenceCandidate.model_validate(copy.deepcopy(old))  # no notes/additional_fields
    with pytest.raises(ValidationError):
        ValueNote(kind="guess", text="x", by="reviewer")


def test_spec_rejects_decided_rule_without_implementation(tmp_path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(
        '{"schema_version": "flag-decisions-v1", "decisions": {"D99": '
        '{"status": "decided", "topic": "t", "rationale": "r", "tests": ["PSI-25/X1"]}}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="No rule"):
        load_spec(path)


def test_d8_keeps_importer_film_with_note() -> None:
    text = "2 cm   0.2 mm PMMA film"
    c = candidate(text, {"geometry": value("Fuel Sample Material", text, "film")})
    rule_d8(Context(c, "D8"))
    assert c["conditions"]["geometry"]["value"] == "film"
    assert "rule-based parser" in c["conditions"]["geometry"]["notes"][0]["text"]
