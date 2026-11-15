"""FLEX PDF extraction stage: plan binding, text-layer checks and guarded execution.

Synthetic pages only; no PDF rendering or provider calls.
"""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from combustion_atlas.ingestion import flex_pdf_run as f

PAGE_47 = "Table 7: Other matrix.\n29 0.50 0.20\n47"
PAGE_48 = (
    "Table 8: CO suppressant efficacy test matrix.\n2\nFuel: C H , Flow: 0.0cm/s\n7 16\n"
    "Test No. P (atm) X\nCO2\n51 0.70 0.25\n52 0.70 0.30\n48"
)
PAGE_49 = "53 0.85 0.25\n49"
PAGE_50 = "Table 9: Next matrix.\n107 0.70 0.25\n50"


def pages(text_48: str = PAGE_48) -> dict[int, dict]:
    texts = {47: PAGE_47, 48: text_48, 49: PAGE_49, 50: PAGE_50}
    return {
        n: {"text": t, "body_text": t.replace("\n7 16", ""), "png": f"png-{n}".encode()}
        for n, t in texts.items()
    }


def loader_for(text_48: str = PAGE_48):
    return lambda path, numbers: {n: pages(text_48)[n] for n in numbers}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(f, "check_source", lambda root: tmp_path / "eird.pdf")
    monkeypatch.setattr(f, "environment", lambda root: {"code": "fixed"})


def cell(page, row, column, text, role="data", span=1, state="present"):
    return f.ExtractedCell(
        page=page,
        row=row,
        column=column,
        row_span=1,
        column_span=span,
        role=role,
        text=text,
        state=state,
        uncertainty=None,
    )


def extraction(cells, rows=5, columns=3, flags=()):
    return f.TableExtraction(
        label="8",
        caption="Table 8: CO2 suppressant efficacy test matrix.",
        header_notes=[],
        rows=rows,
        columns=columns,
        cells=cells,
        footnotes=[],
        context_flags=list(flags),
        uncertainties=[],
    )


def good_cells():
    return [
        cell(48, 0, 0, "Fuel: C7H16 , Flow: 0.0 cm/s", role="row_header", span=3),
        cell(48, 1, 0, "Test No.", role="header"),
        cell(48, 1, 1, "P (atm)", role="header"),
        cell(48, 1, 2, "XCO2", role="header"),
        cell(48, 2, 0, "51"),
        cell(48, 2, 1, "0.70"),
        cell(48, 2, 2, "0.25"),
        cell(48, 3, 0, "52"),
        cell(48, 3, 1, "0.70"),
        cell(48, 3, 2, "0.30"),
        cell(49, 4, 0, "53"),
        cell(49, 4, 1, "0.85"),
        cell(49, 4, 2, "0.25"),
    ]


def test_context_is_table_pages_plus_one_before_and_after() -> None:
    assert f.context_pages([48, 49]) == [47, 48, 49, 50]
    assert f.context_pages([81]) == [80, 81]
    assert f.context_pages([1]) == [1, 2]


def test_plan_binds_requests_and_detects_changed_pages(tmp_path) -> None:
    plan = f.create_plan(tmp_path, ["8"], Decimal("1"), "held_out", loader_for())
    target = plan["targets"][0]
    assert target["table_pages"] == [48, 49] and target["context_pages"] == [47, 48, 49, 50]
    assert set(target["image_sha256"]) == {"48", "49"}  # images of table pages only
    assert f.rebuild(tmp_path, plan, loader_for())
    with pytest.raises(ValueError, match="create a new plan"):
        f.rebuild(tmp_path, plan, loader_for(PAGE_48.replace("0.30", "0.35")))


def test_plan_refuses_missing_caption_and_unknown_tables(tmp_path) -> None:
    with pytest.raises(ValueError, match="caption not found"):
        f.create_plan(tmp_path, ["8"], Decimal("1"), "held_out", loader_for("no caption"))
    with pytest.raises(ValueError, match="not in the FLEX inventory"):
        f.create_plan(tmp_path, ["3"], Decimal("1"), "held_out", loader_for())


def test_clean_transcription_passes_with_displaced_subscripts() -> None:
    issues = f.check_extraction(extraction(good_cells()), pages(), [48, 49])
    assert issues == []


def test_missed_row_and_misread_number_are_flagged() -> None:
    cells = [c for c in good_cells() if c.row != 3]
    issues = f.check_extraction(extraction(cells), pages(), [48, 49])
    missing = next(i for i in issues if i["code"] == "printed_numbers_not_transcribed")
    assert sorted(missing["values"]) == ["0.30", "0.70", "52"]

    cells = good_cells()
    cells[-1] = cell(49, 4, 2, "0.35")
    codes = [i["code"] for i in f.check_extraction(extraction(cells), pages(), [48, 49])]
    assert "cell_text_not_in_text_layer" in codes
    assert "transcribed_numbers_not_printed" in codes


def test_cells_from_context_pages_and_context_flags_are_reported() -> None:
    cells = good_cells() + [cell(50, 4, 0, "107")]
    issues = f.check_extraction(
        extraction(cells, flags=["Which diameter applies per test is not stated"]),
        pages(),
        [48, 49],
    )
    codes = {i["code"] for i in issues}
    assert {"cell_outside_table_pages", "context_needed", "invalid_grid"} <= codes


def test_dry_run_makes_no_calls_and_live_run_records_ledger(tmp_path) -> None:
    root = tmp_path
    plan = f.create_plan(root, ["8"], Decimal("1"), "held_out", loader_for())
    summary = f.execute(root, plan, root / "data/processed/full-runs/x", loader=loader_for())
    assert summary["dry_run"] and not (root / "data/processed/full-runs/x").exists()

    calls = []

    class Responses:
        def parse(self, **kwargs):
            calls.append(kwargs)
            usage = SimpleNamespace(
                model_dump=lambda mode: {"input_tokens": 5000, "output_tokens": 3000}
            )
            return SimpleNamespace(
                output_parsed=extraction(good_cells()), usage=usage, id="r1", model="m"
            )

    client = SimpleNamespace(responses=Responses())
    out = root / "data/processed/full-runs/flex"
    f.execute(root, plan, out, allow_calls=True, client=client, loader=loader_for())
    images = [c for c in calls[0]["input"][0]["content"] if c["type"] == "input_image"]
    assert len(images) == 2  # table pages only; context pages go as text
    result = json.loads((out / "table-08/extraction.json").read_text(encoding="utf-8"))
    assert result["status"] == "unreviewed" and result["check_issues"] == []
    ledger = (out / "run-ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["status"] for line in ledger] == ["reserved", "complete"]
    assert (out / "table-08/review.md").exists() and not (out / ".run-lock").exists()
