# Combustion Atlas

Combustion Atlas is an evidence-preserving research workspace for NASA microgravity-combustion experiments. It keeps raw source values and provenance intact while producing run-level records suitable for audited structured retrieval.

## What it does

Live at **https://combustion-atlas.azurewebsites.net**.

- **Ask:** a chat that answers from 29 indexed NASA reports and PSI tables (BASS, BASS-II,
  FLEX, Saffire). Every claim quotes its source page; numbers are checked against the
  quotes. Supports follow-up questions, figure browsing and reviewed table records.
- **Explore:** experiment coverage heatmaps (which conditions were run or planned) and an
  evidence landscape: a 2-D and rotatable 3-D topic map of every indexed passage, figure
  and table, with related evidence for each item.
- **Sources** and **Add to corpus** (PDF uploads, held for admin approval).

NASA data, generated artifacts, model caches and credentials are not stored in this
repository; see [`docs/local_artifacts.md`](docs/local_artifacts.md).

Architecture, scientific review notes and operating instructions are in [`docs/`](docs/):
the [review workspace guide](docs/review_ui.md) covers experiment field inspection, review
notes, condition filters, cited search and source browsing, and
[`docs/deploy_azure.md`](docs/deploy_azure.md) covers hosting.

## Local setup

The reference environment uses Python 3.12 and [uv](https://docs.astral.sh/uv/). Once uv is installed:

```sh
uv sync --all-groups
cp .env.example .env
uv run pytest
```

Keep `.env` local. Use the data directories only for non-versioned captures and generated artifacts.

## Core commands

```sh
# Check the environment
uv run python -m combustion_atlas.setup

# Produce candidate JSON and the Markdown human-review queue
uv run python -m combustion_atlas.normalization data/raw/bass-ii.csv \
  --source-url https://psi.nasa.gov/physci/repo/data/investigations/PSI-25 \
  --investigation-id PSI-25 --test-ids B1 B2 B3 B4 B5 \
  --output data/review/psi-25-b1-b5.json

# Build page-preserving PDF chunks plus SQLite FTS5 search
uv run python -m combustion_atlas.rag build data/raw/report.pdf --investigation PSI-25

# Generate OpenAI embeddings for the indexed chunks
uv run python -m combustion_atlas.providers embed --allow-provider-calls

# Run hybrid keyword and dense retrieval
uv run python -m combustion_atlas.rag query "oxygen concentration and extinction" \
  --method hybrid --allow-provider-calls

# Launch the local experiment and document-evidence interface
uv run python -m combustion_atlas.app --port 8765
```

## Repository layout

```text
src/combustion_atlas/  Application package
tests/                 Unit tests and versioned fixtures
docs/                  Architecture, scientific review, and operating guidance
data/                  Local NASA captures, review, and retrieval artifacts (ignored)
```

## Evidence policy

NASA PSI/NTRS materials are the scientific source of truth. Normalization must preserve original cells, units, provenance, missing values, and ambiguity; it must never invent experimental values or turn instrument controls into physical measurements without documented calibration.
