# Shared figure and table output contract

Version: `1.0`. Python source of truth:
`src/combustion_atlas/rag/visual_models.py`, model `VisualArtifact`.
Language-independent export: [visual-artifact.schema.json](visual-artifact.schema.json).
The table worker owns complex table transcription; the figure worker does not transcribe tables.

## Handoff for the table worker

Produce UTF-8 JSONL: one `VisualArtifact` per table, one JSON object per line.
Put local outputs under `data/processed/visuals/`. These artifacts are ignored by Git.
Do not edit the figure extraction module or rebuild the shared RAG database.
The importer checks all records with Pydantic, verifies crop hashes and checks
source identity against the existing document index.

```python
from combustion_atlas.rag.visual_models import VisualArtifact, TableContent, TableCell

artifact = VisualArtifact.model_validate(your_table_dictionary)
assert artifact.kind == "table"
assert artifact.table is not None
jsonl_line = artifact.model_dump_json()
```

Required identity and provenance:

- `artifact_id`: stable unique ID, e.g. `<source_id>:p64:table:5.1`.
- `kind`: `table` or `figure`.
- `source_sha256`: full SHA-256 of the original PDF bytes.
- `source_id`: first 16 characters of that SHA-256.
- `filename`: exact filename used by the document index.
- `physical_page`: one-based PDF page, not the printed report page.
- `printed_page`: optional printed page label; never substitute it for physical page.
- `source_url` and `investigation_id`: source metadata when known.
- `label` and `caption`: source table/figure identifier and original caption text.
- `region`: page dimensions and `x0, top, x1, bottom` in PDF points (72/inch),
  origin at top-left. It must be nonempty and inside the page.
- `region.scope`: `isolated` for a true element crop, `page_context` for a full page.
- `crop_path`: relative POSIX PNG path under `data/processed/visuals/`.
- `crop_sha256`: SHA-256 of those PNG bytes. Keep the original crop available.

Table-specific fields:

- `table.rows` and `table.columns` include header rows and columns.
- `table.cells`: zero-based row/column coordinates, raw `text`, optional `unit`,
  `role` (`header`, `row_header`, `data`), and optional spans (`row_span`, `column_span`).
- Each grid position must be covered exactly once. Merged cells are represented
  once with their spans; do not add duplicate placeholder cells under a merged cell.
- Preserve hierarchy with coordinates and spans. Keep header text and unit strings verbatim.
- Missingness is explicit: `present` with nonempty text, `blank` with `text=""`,
  or `unreadable` with `text=null` and a useful `uncertainty` explanation.
- `table.footnotes`: retain source notes, qualifiers and abbreviations.
- Do not silently turn ranges, inequalities or approximations into scalar numbers.

Example table content (synthetic, not a NASA measurement):

```json
{
  "rows": 2,
  "columns": 2,
  "cells": [
    {"row": 0, "column": 0, "role": "header", "text": "Sample"},
    {"row": 0, "column": 1, "role": "header", "text": "Thickness (mm)", "unit": "mm"},
    {"row": 1, "column": 0, "text": "Example A"},
    {"row": 1, "column": 1, "text": "<0.1", "unit": "mm"}
  ],
  "footnotes": ["Synthetic contract example only."]
}
```

Set `method` to `manual`, `table_parser`, or `openai_vision` as appropriate.
For API outputs supply `model`, `prompt_version`, `input_tokens`, and `output_tokens`.
`description`, `visible_labels`, and `uncertainties` are additional searchable context.
Keep `review_status=unreviewed` until a named reviewer verifies the output against
the source. Automated checks are not human approval. Rejected items cannot be indexed.

## Figure extraction and vision

```sh
# Export the machine-readable contract after changing the Pydantic model
uv run python -m combustion_atlas.rag.visuals schema --output docs/visual-artifact.schema.json

# Capture a bounded pilot; no API calls
uv run python -m combustion_atlas.rag.visuals extract data/raw/bass-ii-summary.pdf \
  --pages 64 68 --limit 3 --investigation PSI-25 \
  --source-url https://ntrs.nasa.gov/citations/20210011385 \
  --output data/processed/visuals/figures.capture.jsonl

# Plan vision calls. Add --allow-provider-calls to execute up to --limit calls.
uv run python -m combustion_atlas.rag.visuals describe \
  data/processed/visuals/figures.capture.jsonl \
  --output data/processed/visuals/figures.described.jsonl --model gpt-4.1-mini --limit 3

# Import descriptions, or use the same command for a completed table JSONL
uv run python -m combustion_atlas.rag.visuals index data/processed/visuals/figures.described.jsonl

# Plan only the missing visual-text embeddings. Add --allow-provider-calls to execute.
uv run python -m combustion_atlas.rag.visuals embed --limit 20
```

Figure detection uses explicit caption anchors; it can miss uncaptioned images
and scanned captions. Default crops retain full page context so vector diagrams,
axes and legends are not silently cut off. They are explicitly marked
`page_context`, not claimed to be isolated figures. Caption wrapping and detected
identity require review. Vision descriptions are interpretations and do not digitize
exact chart values. Complex table transcription is left to the separate table worker.

Repeated description runs reuse matching source/crop/caption/region, model and prompt
identities. Outputs are saved after each completed figure. Failed API calls do not
replace earlier successful results. Imports use content fingerprints to invalidate
changed visual chunks and their vectors while preserving unrelated text chunks.
Embedding adds only missing visual vectors; it does not re-embed existing text.
Changes to a full PDF corpus via `rag build` still replace the entire index.

The UI exposes descriptions as derived evidence with original page/crop links.
Citation validation confirms references to retrieved text, not that a generated
description faithfully represents the visual. Verify scientific claims against the crop.
