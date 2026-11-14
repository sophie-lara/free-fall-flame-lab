"""Prepare one background-table candidate for source review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from combustion_atlas.ingestion.pilot_mapping import FLEX_SHA

from .evidence_schema import EvidenceCandidate


def prepare(root: Path) -> dict[str, Any]:
    pdf = root / "data/raw/preserved-review/PSI-69_Engineering Documents_FLEX_EIRD_v4.pdf"
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != FLEX_SHA:
        raise ValueError("FLEX source checksum mismatch")
    url = "https://psi.nasa.gov/physci/repo/data/investigations/PSI-69"
    def cell(column: str, text: str) -> dict[str, Any]:
        return {"original_value": text, "original_unit": None, "provenance": {
            "source_url": url, "file": pdf.name, "row": 2, "column": column,
            "page": 12, "table": "2", "synthetic": False, "source_sha256": FLEX_SHA}}
    agent = cell("Agent/Env.", "He")
    normal = cell("MEC, 1−g", "0.27")
    micro = cell("MEC, μg", "0.31")
    caption = cell("Table 2 caption", "Gaseous fire suppression agent efficacy, as measured "
                   "by the MEC, for cup burner flames (Takahashi et al., 2004).")
    def value(source: dict[str, Any]) -> dict[str, Any]:
        return {**source, "value": source["original_value"], "unit": None,
                "qualifier": None, "uncertainty": None}
    candidate = EvidenceCandidate.model_validate({
        "identity": {"investigation_id": "PSI-69", "test_id": "FLEX-T2-He", "sample_id": "He"},
        "conditions": {"suppression_agent": value(agent)},
        "outcomes": [{**value(normal), "outcome_type": "MEC, 1−g"},
                     {**value(micro), "outcome_type": "MEC, μg"}],
        "instrument_settings": {}, "extra_metadata": {"table_caption": caption},
        "raw_cells": [agent, normal, micro, caption], "extraction_confidence": None,
        "validation_status": "review_required", "human_review_status": "unreviewed",
        "issues": [{"code": "background_study", "field": "context", "severity": "review",
            "message": "Background cup-burner study: source describes normal-gravity tests "
                       "and microgravity simulations; not an individual FLEX flight run."},
            {"code": "units_unverified", "field": "MEC", "severity": "review",
             "message": "Verify the concentration basis and precise simulation context."}]})
    return {"records": [candidate.model_dump(mode="json")]}


def main() -> None:
    root = Path.cwd().resolve()
    result = prepare(root)
    output = root / "data/review/flex-table2-candidates.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("Prepared FLEX Table 2 helium candidate")


if __name__ == "__main__":
    main()
