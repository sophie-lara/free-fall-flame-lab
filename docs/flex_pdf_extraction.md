# FLEX PDF table extraction

Stage 1 of the FLEX PDF pipeline turns a printed table into source-located cells. Mapping
those cells into structured fields is a separate, later stage that starts from reviewed
cells.

## Scope

Source: `PSI-69_Engineering Documents_FLEX_EIRD_v4.pdf` (81 pages, SHA-256
`be236c28…a3ebe9`). Each table is extracted once, from the EIRD.

| Tables | Pages | Evidence class |
|---|---|---|
| 2, 14 | 12, 80 | background data (literature/calculation, not FLEX runs) |
| 6, 7, 11, 12 | 46, 47, 54, 55 | planned test matrix (planned conditions, not results) |
| 8, 9, 10 | 48–49, 50–51, 52–53 | planned test matrix |
| 13 | 76 | background data; regression only (used during development) |

Excluded: Table 1 (formulas set out as a table; reviewer decision), Tables 3–5 (requirements lists) and the Test Plan's copies of Tables 2 and 6–12.
Comparing those copies against the EIRD extraction remains optional.

Table 8 is the held-out table: the extraction instructions are not tuned on it, and its
output is compared with an independent human check before other tables are run.

## What each request sends

- Images of the table's own pages (150 dpi, high detail).
- The PDF text layer of the table pages **plus one page before and one after**
  (2 + n pages for an n-page table). The model is told those extra pages are context
  only and must not supply cells.

The model returns every cell with its physical page, zero-based grid position, spans and
role. Full-width rows such as condition statements or a fuel change are `row_header`
cells spanning all columns. It also lists anything needed to interpret the table that is
not on the supplied pages (`context_flags`).

## Automatic checks (no model calls)

- **Grid validity:** no overlapping cells, and the grid matches the declared size.
- **Numeric cells:** text must appear exactly in that page's text layer.
- **Completeness:** every all-numeric line on the table pages must be fully transcribed,
  and no data cell may contain a number those lines lack. Subscripts are printed smaller
  and are dropped for this count.
- **Header and label cells:** checked by words and numbers, because the text layer moves
  subscripts (O2, CO2, C7H16) onto other lines. A wrong short label (e.g. `XHe` for
  `XCO2`) can slip through, so the human check must cover headers.
- **Flags passed through to review:** cells the model marked unreadable or uncertain, cells
  taken from context pages, and context flags.

## Commands

```bash
.venv/Scripts/python.exe -m combustion_atlas.ingestion.flex_pdf_run plan --tables 8 --stage held_out --budget 1.00 --output data/processed/flex-pdf-plan-table8-v1.json
.venv/Scripts/python.exe -m combustion_atlas.ingestion.flex_pdf_run run --plan data/processed/flex-pdf-plan-table8-v1.json --output data/processed/full-runs/flex-pdf-table8-v1
```

## Stage 2: test-matrix mapping

`combustion_atlas.ingestion.flex_mapping` starts only from extractions with a recorded
human check (reviewer and time are stored in the plan). One model call per table sends
the extracted cells plus the text of the same 2 + n pages, and returns a table-level
mapping: what each column holds, every condition stated in each full-width condition
row (with a verbatim excerpt), the evidence class with its quoted basis, and anything
not apparent from those pages. Per-test records (`FLEX-T<table>-<test no.>`) are then
expanded by code, so every value is copied from the checked cells, never re-typed by the
model. Each value is located by PDF page, table and row, and records carry
`additional_fields` and per-value notes like the CSV run.

These rules apply whatever the model answers:
- A condition row applies to the rows below it until the next one, which overrides only
  the fields it states (e.g. a fuel change).
- A condition listing several values without assigning them per test (e.g.
  `D0 = 3, 5 mm`) is kept as written with an *ambiguous* note on every record. If the
  model called it single, validation also flags that.
- A formula (e.g. `XN2 = 1.0 − XO2 − XCO2`) is kept as an additional field, not computed.
- Every planned-matrix record is labelled a planned test condition, not an observed
  result.

```bash
.venv/Scripts/python.exe -m combustion_atlas.ingestion.flex_mapping plan --extraction data/processed/full-runs/flex-pdf-table8-v1/table-08/extraction.json --reviewer Sophie --reviewed-at 2026-11-14T18:40:00-06:00 --output data/processed/flex-mapping-plan-table8-v1.json
.venv/Scripts/python.exe -m combustion_atlas.ingestion.flex_mapping run --plan data/processed/flex-mapping-plan-table8-v1.json --output data/processed/full-runs/flex-mapping-table8-v1
```

### Combining tables and attaching reviewer notes

`flex_mapping annotate` combines the per-table candidate files into one file. It
refuses any table without a recorded extraction check, or whose mapping changed after
its candidates were written, and any duplicate test identity. It then attaches the
reviewer's record notes from `docs/review_decisions/flex-eird-tables-v1-review.json` as
record-level issues, so cards show them:
- **N1:** EIRD p. 45 says the matrices are for planning and not the final test matrix.
- **Spot checks:** a note on tables whose transcription was only spot-checked.

```bash
.venv/Scripts/python.exe -m combustion_atlas.ingestion.flex_mapping annotate --review docs/review_decisions/flex-eird-tables-v1-review.json --candidates <table candidates.json files> --output data/processed/flex-matrix-candidates-v1.json
```

The current output is 290 unreviewed planned-test records (tests 1–290, Tables 6–12).

Background tables (2, 14) are not mapped to fields. They are meant to appear as
verbatim cell cards with headers, caption and page links.

Both run commands are dry runs unless `--allow-provider-calls` is added. A plan freezes the
source hash, pages, page-image hashes, request hash, code and library versions, model and
a conservative cost reservation; any change requires a new plan. Each table is reserved in
`run-ledger.jsonl` before its request is sent. Outputs per table are the page images,
`extraction.json` and `review.md`, all unreviewed.

## Reviewed evidence for the bridge

`combustion_atlas.review.flex_reviewed` promotes the FLEX results after the reviewer's
decision (recorded under `promotion` in the review record). It writes
`data/processed/reviewed-evidence-flex-v1.json` and its decisions file, which the bridge
loads like the CSV pair:
- 290 `planned_test_condition` records (Tables 6–12). These appear as cards labelled
  "planned test condition, not an observed result" and never become coverage runs.
- 6 `background_table_row` records (Tables 2 and 14). Every cell is kept verbatim as an
  additional field. Table 14 cells carry the reviewer's symbol definitions as
  `definition` notes.

Each record keeps its notes, the N1 note and, where relevant, the spot-check note. All
inputs are verified by hash.

```bash
.venv/Scripts/python.exe -m combustion_atlas.review.flex_reviewed
```
