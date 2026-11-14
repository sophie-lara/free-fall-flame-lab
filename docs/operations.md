# Operations

Run application commands from the repository root. Python 3.12 and `uv` are required.

## Environment

```sh
sh scripts/bootstrap.sh
```

The bootstrap installs the locked dependencies, creates `.env` from `.env.example` when needed, runs diagnostics, and executes the test suite. Keep API keys only in `.env`; the file is ignored by Git.

For OpenAI document embeddings, configure:

```dotenv
OPENAI_API_KEY=
COMBUSTION_ATLAS_EMBEDDING_PROVIDER=openai
COMBUSTION_ATLAS_EMBEDDING_MODEL=text-embedding-3-small
COMBUSTION_ATLAS_EMBEDDING_DIMENSIONS=1536
```

Generated answers remain disabled unless an answer provider is configured separately.

## Candidate normalization

```sh
uv run python -m combustion_atlas.normalization data/raw/bass-ii.csv \
  --source-url https://psi.nasa.gov/physci/repo/data/investigations/PSI-25 \
  --investigation-id PSI-25 \
  --test-ids B1 B2 B3 B4 B5 \
  --output data/review/psi-25-b1-b5.json
```

This produces candidate JSON and `data/review/psi-25-b1-b5.md`. Candidate generation does not imply scientific acceptance.

## Document index

Build page-preserving chunks and the keyword index:

```sh
uv run python -m combustion_atlas.rag build data/raw/report.pdf --investigation PSI-25
```

Create OpenAI embeddings only after inspecting the chunk build report:

```sh
uv run python -m combustion_atlas.providers embed \
  --database data/embeddings/rag.sqlite3 \
  --allow-provider-calls
```

The explicit flag prevents accidental billable API calls. Embedding inputs are the extracted document chunks stored in the local index.

Query keyword, dense, or hybrid retrieval:

```sh
uv run python -m combustion_atlas.rag query "oxygen concentration and extinction" \
  --method hybrid \
  --database data/embeddings/rag.sqlite3 \
  --allow-provider-calls
```

## Review and adjudication

```sh
uv run python -m combustion_atlas.review prepare \
  --candidates data/review/psi-25-b1-b5.json \
  --output data/review/decisions.template.json
```

Complete a copy of the template, then apply it to a new audit artifact:

```sh
uv run python -m combustion_atlas.review apply \
  --candidates data/review/psi-25-b1-b5.json \
  --decisions data/review/decisions.completed.json \
  --output data/processed/adjudication-001.json \
  --gold-dir data/processed/gold
```

## Local interface

```sh
uv run python -m combustion_atlas.app --port 8765
```

Open `http://127.0.0.1:8765`. The server binds only to the loopback interface.

## Verification

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
node --check src/combustion_atlas/app/static/app.js
uv build
```
