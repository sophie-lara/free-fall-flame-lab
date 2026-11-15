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

To enable cited answers, set `COMBUSTION_ATLAS_ANSWER_PROVIDER=openai` and
`COMBUSTION_ATLAS_ANSWER_MODEL` to an available Responses API model supporting
structured outputs in your local `.env`. The model is deliberately explicit.
The UI reads configuration after a page refresh; it never receives the API key.

In **Ask the evidence**, choose keyword, semantic, or hybrid retrieval. Semantic
retrieval requires document embeddings generated for the configured embedding
model. Enable OpenAI calls for a query to use semantic retrieval or generated
answers. Questions are sent for embeddings; retrieved passages are also sent
when generating answers. Keyword-only search uses local storage.

Answers contain individual claims, exact supporting excerpts, and references
to retrieved chunks. Unknown references and excerpts absent from the supplied
passages cause the response to fail validation. These checks verify citation
identity and excerpt presence, not scientific entailment or numerical correctness.
An empty retrieval result or unsupported question yields insufficient evidence.
The answer path uses document passages and does not treat candidate experiment
records as approved evidence. Proposed-condition matching remains a candidate
preview in the experiment browser.

The answer provider makes at most two generation attempts per query. If the
first draft fails citation/excerpt validation, it requests one repaired draft;
the same checks apply to the repair. Failed drafts are never shown as answers.

### First real-document pilot

The local pilot uses the public [BASS-II Summary Report, NASA/TM-20210011385](https://ntrs.nasa.gov/citations/20210011385).
The captured PDF SHA-256 is
`5ffa911fd9b6356f204646003fb9342e341810dcdfdf5cb15756e7f01ec5f770`.
Capture metadata is in `data/raw/bass-ii-summary.capture.json`.
The index contains 144 physical pages and 159 chunks; eight pages were flagged
as sparse or image-heavy. Figure and table completeness is not established.
PDF physical page numbers differ from printed report page numbers.

The pilot generated 159 actual OpenAI `text-embedding-3-small` vectors, each with
1,536 dimensions, in the ignored local SQLite database. Local answer generation
uses `gpt-4.1-mini`; configure your own `.env` when setting up another workspace.
Keys, reports, generated answers, and vector artifacts are not versioned.

Reproduce a bounded live search and cited answer after building the index and
embeddings as described below:

```sh
uv run python -m combustion_atlas.rag query \
  "Which variables were tested in BASS-II?" \
  --investigation PSI-25 --method hybrid --allow-provider-calls --answer \
  --output data/processed/rag/pilot-answer.json
```

This is a development smoke check, not a reviewed retrieval benchmark or
scientific validation. Next, review known-answer questions and expected source
pages, include unsupported questions, and compare retrieval methods. Avoid
rebuilding this corpus accidentally: the current build replaces the index and
its stored vectors, which then need regenerating.

In the first live smoke check, the variables question ranked physical page 11
first and produced a citation-validated answer. A question requesting measured
titanium-alloy flame-spread rates at Martian surface pressure returned
`insufficient_evidence` with no claims. Local responses are saved as
`data/processed/rag/pilot-answer.json` and `pilot-no-evidence.json`.

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

Figure extraction and the shared table handoff are documented in
[visual_artifacts.md](visual_artifacts.md). The Pydantic contract is
`combustion_atlas.rag.visual_models.VisualArtifact`; a language-independent
[JSON Schema](visual-artifact.schema.json) is exported alongside that guide.
Complex table transcription remains a separate worker's responsibility.

Build page-preserving chunks and the keyword index for an **empty** database:

```sh
uv run python -m combustion_atlas.rag build data/raw/report.pdf --investigation PSI-25
```

`build` replaces the whole corpus, every vector namespace and all visual artifacts,
so it refuses to run on a populated index unless `--replace-existing` is given.
Add further documents incrementally, one PDF per call so each keeps its own
investigation and source metadata:

```sh
uv run python -m combustion_atlas.rag add data/raw/new-report.pdf \
  --investigation SAFFIRE-I --source-url https://ntrs.nasa.gov/citations/...
uv run python -m combustion_atlas.providers embed --missing-only            # plan
uv run python -m combustion_atlas.providers embed --missing-only --allow-provider-calls
uv run python -m combustion_atlas.rag remove <source_id>   # one source, its vectors and visuals
```

`add` reports `unchanged` for an already indexed file and refuses a different
file whose source ID collides. Per-source page/chunk JSONL is written under
`data/processed/rag/sources/`; the original build files are not overwritten.
Back up `data/embeddings/rag.sqlite3` (e.g. `sqlite3 ... ".backup ..."`) first.

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

Keyword search drops question words and ORs the remaining terms with Porter
stemming, so natural-language questions do not need every word to match. Opening
an older database rebuilds only the derived `chunks_fts` index; chunks and vectors
are unchanged.

### Retrieval and answer evaluation

Question files follow `combustion_atlas.evaluation.retrieval.EvalQuestion`:
expected pages, visual element IDs or chunk IDs; expected status
(`answered` or `insufficient_evidence`); required answer terms; and a
`development` or `heldout` split. Only reviewed questions are scored by default.

```sh
# Free: keyword only
uv run python -m combustion_atlas.evaluation questions.json \
  --split development --output data/processed/eval/report.json
# Billable: compare methods and score answers (draft run on unreviewed questions)
uv run python -m combustion_atlas.evaluation questions.json --split development \
  --methods keyword dense hybrid --answers --include-unreviewed \
  --allow-provider-calls --output data/processed/eval/report.json
```

Reports bind results to the question-file hash, Git commit and dirty state, a
chunk-content fingerprint, document hashes, vector namespaces, visual fingerprints
and configured models. Retrieval metrics (hit@3/5, MRR@5, element hit@5) are
reported separately from answer checks (status, required terms, numbers missing
from the claim's own quotes). Visual-description fidelity is flagged for manual
review. Do not tune retrieval against the held-out split.

### Reviewed table evidence in retrieval and coverage

`analysis.evidence_bridge` implements the RAG side of
[rag_adapter_handoff.md](rag_adapter_handoff.md). It reads every
`data/processed/reviewed-evidence*.json` with its matching
`reviewed-decisions*.json` (e.g. the committed `-csv-run-v1` pair), rejects pairs
marked `draft` and identities that appear in more than one file, then:

```sh
uv run python -m combustion_atlas.analysis.evidence_bridge report   # verify only
uv run python -m combustion_atlas.analysis.evidence_bridge sync     # index record cards
uv run python -m combustion_atlas.providers embed --missing-only --allow-provider-calls
```

The decisions file must hash-match the evidence bytes, and each record must match its
decision (identity, source hash, candidate and reviewed fingerprints) and validate as
`EvidenceCandidate`; otherwise it is rejected with a reason. Record cards quote source
cells verbatim and keep derived values, review state, open questions and CSV/PDF
locators separate (CSV cards have no page: page 0). Coverage uses reviewed values in
place of table-parsed ones only where conversion is faithful (numeric, known unit, no
qualifier); everything else is listed under `unconverted`. Background table rows
become cards but not coverage runs. Value `notes` (kind, author, decision) and
`additional_fields` are printed on cards; additional fields are never mapped. Numbers
stored as plain numeric text are accepted; values with `unresolved`, `ambiguous`,
`pending` or `inferred` notes stay out of coverage (`assumed`/`model` notes are
allowed). Rows marked `pattern_rule_only` are labelled "not individually reviewed"
and excluded from coverage. A question that names a test ID ("O12", "2-8") pins that
record card first. Answers prefer record cards for exact values and
label each claim's evidence type.

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

The home page (`#ask`) answers questions across the indexed corpus with cited
passages. `#corpus` shows per-document page strips (text density, figures,
sections from top-level headings), a topic map (2-D principal-component
projection of stored embeddings, cached in `data/processed/rag/topic-map.json`;
axes have no units), and a PDF upload that saves to `data/raw/uploads/` and runs
`rag add` (optionally embedding the new passages). `#directions` returns cited
findings, author-stated open questions, collection gaps, and suggested next steps
that must reference those citations; suggestions are not validated
recommendations. Review pages (overview, experiments, conditions, sources) are
under "Review workspace" in the sidebar.

For the local text-RAG POC, open `http://127.0.0.1:8765/#search` after launching
the app below. With matching stored embeddings and a configured answer model,
the UI selects hybrid search and cited answers. Each submitted query uses OpenAI;
the settings panel shows the selected behavior and permits local keyword-only search.
The readiness banner shows the number of stored embeddings.

Try the built-in questions about BASS-II variables and test counts. Then try
the titanium/Martian-pressure question to check insufficient-evidence behavior.
Use **View supporting passage** and **Open cited page** to inspect answers.
Check relevance, citation correctness, qualifications and numerical values.
Tables and figures do not yet have dedicated extraction in this POC.

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
