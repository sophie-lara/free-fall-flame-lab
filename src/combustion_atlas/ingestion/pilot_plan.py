"""Prepare an offline, source-bound pilot manifest; never calls a provider."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

SELECTION = {
    "PSI-25": {"B1": "development", "B2": "development", "B3": "holdout",
               "B4": "development", "B5": "development"},
    "PSI-69": {"FLEX-T13-Ar": "development", "FLEX-T13-N2": "holdout",
               "FLEX-T13-He": "development"},
    "PSI-99": {"SAFFIRE-II-2-1": "development", "SAFFIRE-II-2-2": "development",
               "SAFFIRE-II-2-4": "holdout"},
}


def prepare(workspace: Path) -> dict[str, object]:
    evidence = workspace / "data/processed/reviewed-evidence-v1.json"
    records = json.loads(evidence.read_text(encoding="utf-8"))["records"]
    selected = []
    for investigation, tests in SELECTION.items():
        for test, split in tests.items():
            matches = [r for r in records if r["investigation_id"] == investigation
                       and r["test_id"] == test]
            if len(matches) != 1:
                raise ValueError(f"Missing or duplicate reviewed record: {investigation}/{test}")
            record = matches[0]
            cell = record["original_candidate"]["raw_cells"][0]["provenance"]
            source = workspace / "data/raw/preserved-review" / cell["file"]
            if hashlib.sha256(source.read_bytes()).hexdigest() != record["source_sha256"]:
                raise ValueError(f"Source checksum mismatch: {source.name}")
            selected.append({"investigation_id": investigation, "test_id": test, "split": split,
                             "source_file": str(source.relative_to(workspace).as_posix()),
                             "source_sha256": record["source_sha256"], "row": cell["row"],
                             "page": cell["page"], "table": cell["table"]})
    flex = next(x for x in selected if x["test_id"] == "FLEX-T13-N2")
    pdf = PdfReader(workspace / str(flex["source_file"]))
    page = int(str(flex["page"]))
    if page <= 1 or page >= len(pdf.pages):
        raise ValueError("FLEX context pages are outside the PDF")
    return {"schema_version": "pilot-plan-v1", "model": "gpt-6-luna", "budget_usd": 2,
            "records": selected, "flex_context_physical_pages": [page - 1, page, page + 1],
            "flex_context_text_characters": [len(pdf.pages[i-1].extract_text() or "")
                                             for i in (page-1, page, page+1)],
            "evaluation_note": "Holdout review decisions and expected values must not be "
                               "included in model prompts; FLEX context is source material.",
            "ready_to_call": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = prepare(args.workspace.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"records": sum(len(tests) for tests in SELECTION.values()),
                      "ready_to_call": False}))


if __name__ == "__main__":
    main()
