# Table transcription handoff

This is a preliminary, unreviewed transcription path. It does not update the review UI,
create approved experiment records, or establish that an LLM response is correct.

`ingestion.llm_handoff` captures a CSV record or a `VisualArtifact` table as source
cells. The PDF handoff includes artifact and page identity, zero-based cell coordinates,
roles, spans, caption and footnotes. CSV record numbers use the parser's one-based
record count (the header is record 1); quoted multiline records are not physical line
numbers. Exact cell text and source SHA-256 are preserved. The referenced visual table
transcription may itself be unreviewed. PDF manifest crop checks do not independently
verify the PDF bytes: verify the original source separately before trusting an artifact.

Run from the repository root. The following prepares a single request and prints its
scope without calling a provider or writing output (choose an actual local CSV and record):

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.ingestion.llm_transcribe data/raw/example.csv --record 2 --model MODEL_NAME --output data/processed/proposal.json
```

For an existing table artifact, use `--visual-manifest MANIFEST.jsonl --artifact-id ID`
instead of the CSV path and `--record`. The manifest and crop must already exist.
The preview gives input characters, not a token or price estimate. A later explicitly
authorized run can add `--allow-provider-calls` to send one request using the process's
`OPENAI_API_KEY`; it limits output tokens, not total cost. The source cells and context
are sent to the provider, so inspect the selected input before enabling calls.

The JSON output contains the source snapshot, proposal, source-link checks, prompt hash,
model, and token usage. A companion `.review.md` shows structured issues. Outputs are
unreviewed, and existing output paths are not intentionally overwritten. Source references
are checked for valid indexes, but the checks cannot establish scientific correctness,
completeness, or that the chosen evidence supports the mapping. Model-declared uncertainty
is not a substitute for independent verification. A zero-issue report is not approval.

Before a pilot, agree on the model, inputs and data handling, budget and call limits,
reviewed examples, and held-out evaluation split. A conversion from proposals to the
existing `EvidenceCandidate` and then `ExperimentRecord` is still needed, including
explicit handling of background rows and source-defined missingness. The review UI reads
native candidate batches and cannot yet consume this output. Do not index the proposal as
reviewed or promote it as a trusted run.

## Bounded pilot

The local `data/processed/pilot-plan-v1.json` selects 11 records and three held-out
records. To inspect the scope without calling a model:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.ingestion.pilot_runner --plan data/processed/pilot-plan-v1.json --output data/processed/pilot-results-v1
```

The runner verifies source hashes and the fixed record selection, then prepares one
request per record. FLEX requests contain previously captured table cells and text
extracted from physical PDF pages 75–77, including other source rows. They do not
include review notes, expected answers, page images, or the PDF itself. This tests
mapping the captured transcription, not reading it from the image. No reviewed
examples are included in requests. The separate evaluation command reads the held-out
references locally after the run.

Adding `--allow-provider-calls` runs the requests. Outputs are unreviewed JSON and
Markdown issues. The runner creates a new output directory, records a reservation
before each call, makes no automatic retries, and stops on errors or missing usage.
It refuses to reuse the directory. After an interrupted request, inspect the ledger
and provider account before considering another run.

The $2 per-run gate reserves a conservative estimated maximum before any request,
using UTF-8 bytes plus framing as a token allowance, 2,500 output tokens per call,
and assumed rates of $0.20/million input and $1/million output tokens. It stops if
reported usage exceeds a reservation. **This is not a provider-enforced billing
limit**: allowances and prices are assumptions, pricing can change, uncertain
failures may incur charges, and other runs or API use are not included. Verify
pricing and the account limit before running. A reservation is not a price quote.

After a complete run, create a local comparison packet without an API call:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.ingestion.pilot_evaluate --results data/processed/pilot-results-v1 --evidence data/processed/reviewed-evidence-v1.json --output data/processed/pilot-holdouts-v1.json
```

The packet places proposals alongside reviewed references and unresolved questions
for manual comparison; it does not calculate accuracy or certify records. Missingness
statuses are `source_marker`, `source_blank`, `unreadable`, `not_found_in_source`,
`mapping_uncertain`, `inferred`, and `reported`. Original text is preserved. Model
labels are proposals, not proof; the model can omit a field entirely, and automatic
checks cannot establish completeness or scientific accuracy.

The pilot adds a source-hash-scoped Table 13 mapping. It preserves each source
cell and its unit independently of the model proposal; `d` and `k` remain proposed
interpretations with `unverified_field_mapping` issues and source page references.
It does not generalize those mappings to other documents. The source-coverage rule
flags unreferenced source cells but cannot establish that the model extracted every
meaning from a cell. BASS material dimensions come from the deterministic parser.
The previously reviewed B2, B4 and Saffire 2-4 ambiguities are retained for their
exact source hashes and cells. Model uncertainty comments are still preserved as
model-generated issues, so those comments may vary between responses.

To reapply local rules to the saved pilot without calling the provider:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.ingestion.pilot_reassess --results data/processed/pilot-results-v3 --output data/processed/pilot-reassessment-v2.json
```

The output records the SHA-256 of each original result and does not overwrite it.
Its source mappings and flags are still unreviewed candidates; they do not create
records for the existing review UI or automatically validate scientific meaning.
