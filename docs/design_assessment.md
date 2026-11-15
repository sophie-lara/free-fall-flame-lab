# Design and implementation assessment

Assessment date: 2026-11-14.

Scope: the working tree on `codex/review-ui`, based on commit `f596c10`, including
the review-interface changes. This is a code and local behavior assessment, not
scientific approval of NASA records or a measured model-accuracy evaluation.

## Overall assessment

The architecture follows the problem statement: run-level structured evidence
and page-preserving document evidence remain independent, source strings and
checksums are retained, instrument settings are separate, and prediction is not
required for the core product. The module boundaries are appropriate for the MVP.

The implementation is an executable engineering foundation, but it does not yet
establish the plan's central claim of scalable, provenance-preserving agentic
normalization. Several evidence-integrity defects need correction before bulk
extraction, gold-fixture promotion, or claims of scientific comparability.

Keep the architecture. Prioritize lossless capture, qualified extraction,
validation, and auditable adjudication ahead of further dashboard features,
large embedding runs, generated scientific answers, or prediction.

## Alignment and progress

| Area | Evidence in this working tree | Assessment against the plan |
| --- | --- | --- |
| Environment | Python package, `uv.lock`, bootstrap scripts, diagnostics, Windows/Linux CI definition | Suitable local foundation; exact run manifests and scientific verification remain separate. |
| Source capture | Explicit URL download, size limit, checksum and capture manifest | Fits bounded ingestion; investigation discovery and heterogeneous source adapters are not provided. |
| Run schema | Conditions, outcomes, instrument settings, raw cells, provenance | Correct separation; missingness, qualitative values, and review state need stronger representation. |
| Normalization | Explicit BASS-II aliases and deterministic material/geometry recognition | Bounded baseline; no LLM mapping proposer or general investigation-adapter harness. |
| Validation | Initial oxygen range and instrument-setting flags | Too narrow to support the broader schema or safely scale extraction. |
| Review | Fingerprinted decision templates, audit output, optional gold export; UI draft notes | Useful structure; approval and correction contracts have integrity gaps. |
| Structured search | Investigation/material/geometry/oxygen filters; UI pressure/airflow/gravity filters | Exact filtering is present; candidate search is not similarity or scientific comparability ranking. |
| Document retrieval | Native PDF text, physical pages, overlapping chunks, SQLite FTS5, OpenAI dense retrieval and rank fusion | Useful retrieval baseline; multi-investigation corpus management and evaluated retrieval quality need work. |
| Review interface | Overview, condition/outcome/raw-cell tabs, draft notes, source library, cited keyword search | Supports inspection; browser search is lexical, and formal adjudication remains a CLI workflow. |
| Evaluation | Reviewed-question lexical hit@3/5 and MRR@5 | Initial harness only; no normalization-quality benchmark or verified scientific accuracy result. |
| Scenario product | No implemented condition-mismatch ranking or DIRECT/ANALOGOUS/MECHANISTIC/GAP policy | An explicit later milestone requiring reviewed semantics, not a missing prerequisite for basic transcription. |
| Prediction | No prediction component | Consistent with its stretch-goal status. |

The tracked raw fixture contains two example BASS-II-shaped rows. The tracked gold
fixture directory contains only `.gitkeep`. The evaluation template contains one
unreviewed question. These artifacts do not substantiate completed B1-B5 scientific
review, multi-investigation extraction accuracy, or a retrieval benchmark.

## Findings requiring attention

Priority P1 means resolve before scaling or promoting trusted scientific artifacts.
P2 means address in the next implementation stages. Missing planned features are
distinguished below from reproduced behavioral defects.

### P1: CSV capture can silently discard source evidence

Location: `ingestion/table_parser.py`, `read_csv_losslessly`.

Synthetic probes reproduced:

- `A,A` with values `first,second` produces only `{"A":"second"}`.
- A two-column header followed by a three-cell row silently drops the extra cell.
- A short row is accepted and filled with `None`, without identifying malformed
  row structure separately from a source blank.

This contradicts the architecture's lossless-ingestion requirement. Reject blank
or duplicate/ambiguous headers and mismatched row widths before semantic mapping.
Preserve original header/value strings, field positions, and record numbers.
Add regression cases for quoted multiline fields and whitespace-equivalent
headers as well as ordinary valid CSVs.

### P1: Numeric parsing changes scientific meaning

Location: `normalization/extractor.py`, `_number` and `_measurement`.

The extractor searches for the first number rather than parsing the complete
source expression. Probes reproduced these normalized values with no qualifier:

| Source text | Result | Problem |
| --- | --- | --- |
| `21-23` | `21.0` | Range becomes an exact lower-end value. |
| `~21.5` | `21.5` | Approximation is lost from normalized semantics. |
| `<0.1` | `0.1` | Bound becomes an exact measurement. |
| `1e-3` | `1.0` | Scientific notation is numerically misread. |

The raw string survives, but structured filters use the changed scalar value.
These examples can also receive `validated` status under the current checks.

Use complete-expression parsers for supported scalar notation, explicit units,
approximations, ranges, and bounds. Quarantine unsupported forms instead of
coercing their first number. Decide explicitly how qualified values participate
in numerical filters; preserving only the original string is insufficient.

### P1: Adjudication does not enforce a sufficient evidence contract

Locations: `review/models.py`, `review/workflow.py`,
`retrieval/__main__.py::_load`.

The source-candidate fingerprint check is valuable. However, a synthetic decision
file was accepted with empty supporting references, a timezone-naive timestamp,
and two decisions for the same candidate. It produced two accepted entries.
Accepting an oxygen-120 candidate changed its deterministic status from
`review_required` to `validated` without resolving the numerical flag.

Code inspection also shows:

- Corrected records are checked for unchanged run identity, but raw evidence and
  source provenance can be replaced without a correction-boundary check.
- Corrected measurements are not passed back through deterministic validation.
- Gold/audit destinations are written without immutable-output or all-destination
  preflight checks; a later failure can leave partial output.
- Approved structured loading trusts an `accepted_records` array. A synthetic
  artifact containing that array alone loaded without decisions or an audit.

Separate human acceptance from deterministic validation. Require substantive
supporting references, nonblank reviewer/rationale, timezone-qualified timestamps,
unique decision identities, and exact candidate bindings. Preserve original raw
evidence and make corrections traceable to source locations. Revalidate corrected
records and preserve unresolved scientific flags. Verify approved artifacts against
their candidate-bound decisions, and write distinct, preflighted audit/gold outputs.

### P1: Validation and schema semantics do not cover the supported evidence

Locations: `normalization/schema.py`, `normalization/validate.py`.

Validation currently checks only initial oxygen range and the presence of
instrument settings. It can overwrite a record's existing validation state and
messages rather than preserving independent extraction/review issues.

`Measurement.value` accepts only numeric values or null. Qualitative outcomes
therefore lack a typed normalized representation. Source blanks, literal missing
markers, absent fields, failed extraction, and unresolved interpretation have no
explicit distinct states. Probes with `none`, literal `null`, `n/a`, and a blank
all produced normalized null with no qualifier. Their raw strings remain distinct,
but the normalized state cannot explain the difference.

Expand the schema deliberately before adding heterogeneous investigators. Preserve
source markers without assuming their meaning. Represent qualitative outcomes and
numeric qualifiers explicitly. Require finite numeric values, known units, suitable
field-level checks, and retained extraction issues. Keep unusual source readings
for review rather than silently correcting or rejecting them.

### P2: The normalization harness is not yet the planned agentic system

Location: `normalization/extractor.py` and the normalization CLI.

This is a deterministic BASS-II extractor. It independently recognizes explicit
PMMA and film text, but does not populate dimension measurements from the material
description. A probe with an explicit thickness/width description left
`conditions.dimensions` empty. Extraction confidence is assigned the constant
`1.0`; it is not an evaluated confidence estimate.

The CLI does not verify that every requested test ID was found and can write an
empty batch successfully. There are no FLEX/Saffire adapters or LLM proposal,
prompt-versioning, response-cache, or normalization-evaluation workflows.

Complete independently supported field extraction and requested-ID checks. Leave
confidence unset or identify it as an uncalibrated method property. Then add a
provider-neutral proposal interface over immutable source evidence: typed output,
source-backed field references, deterministic validation, quarantined ambiguities,
and recorded prompt/model/schema/code versions. Treat this as the core product
milestone rather than inferring completion from document embeddings.

### P2: Embedding responses need stronger alignment and vector checks

Locations: `providers/openai_embeddings.py`, `rag/vectors.py`, `rag/store.py`.

Mocked responses with duplicate response indexes and responses containing a NaN
component were accepted by the embedding adapter. Sorting indexes and checking
count/dimensions does not prove that each input has exactly one corresponding
valid vector.

Require the complete index set exactly once, finite components, nonzero vectors,
and validated vector encoding. Check request/token limits before batch execution
and preserve the existing atomic replacement behavior. Record model and input
identities plus usage/cost metadata before running large paid batches.

### P2: Corpus builds do not yet manage a heterogeneous archive

Locations: `rag/build.py`, `rag/store.py`.

Code inspection shows each build replaces the entire document index and its
vectors. All PDFs in an invocation receive one shared investigation/source URL;
page records have a single investigation ID. Exact duplicate bytes are skipped
without retaining all alternate source associations. Chunk IDs encode source,
page, and ordinal, but not changed chunking parameters or chunk content.

This is adequate for a documented single-corpus rebuild, but not incremental
cross-investigation ingestion. Use per-document source manifests and explicit
replacement/upsert semantics, retain alternate associations, fingerprint extraction
and chunking configuration, and surface table/layout limitations. Citation and
evaluation references must detect stale chunk identities after a rebuild.

### P2: Review UI and evaluation are not yet a closed scientific feedback loop

Locations: `app/server.py`, `app/public/app.js`, `evaluation/lexical.py`.

UI notes are correctly separate from candidate mutation, but bind only to
investigation/test IDs, not the exact candidate fingerprint. Regenerating a
candidate can leave an earlier draft displayed against changed content. The
display's human-review state is always `unreviewed`; it does not read an
adjudication result. Add fingerprinted draft context and explicit stale-note
handling, then expose verified adjudication state separately.

Evaluation currently trusts a question's `reviewed` boolean without enforcing
reviewer, source/reference validity, or nonempty expected references. It scores
lexical chunk IDs only, with no source/page equivalence, normalization metrics,
negative-case design, or input/index/configuration hashes in the result artifact.

Establish human-reviewed gold fixtures and held-out examples before evaluating
automation. Measure field mapping, unit correctness, qualifier/missingness
preservation, provenance, false inference, and appropriate review routing.
Evaluate keyword/dense/hybrid retrieval separately from answer adequacy and
scientific comparability.

## Setup and implementation conditions

- Local diagnostics pass on Python 3.12.14 with SQLite FTS5 and the required
  runtime modules available.
- `uv.lock` provides a useful dependency baseline. Python is selected by minor
  version in bootstrap scripts; the build backend uses a lower bound. Record
  exact interpreter, dependencies, build tooling, lock hash, and artifact inputs
  for a replayable run rather than assuming byte-identical builds.
- CI declares Windows/Linux lint, formatting, typing, tests, and packaging. This
  assessment verifies Windows locally; remote CI/Linux results are not established
  by those local checks. Add JavaScript syntax and UI smoke coverage to CI.
- The application is loopback-only, uses local assets, validates note writes,
  and restricts captured-file serving to matching raw-directory bytes. Keep it
  local until deployment/authentication/multi-user requirements are defined.
- Candidate loading follows filename conventions and scans supplemental batch
  artifacts. Prefer a documented project manifest as the set of investigations
  and reviewed batches grows.
- Embedding and answer provider configuration are separate. The implemented
  provider performs embeddings; answer-provider settings alone do not implement
  grounded answer generation or an LLM normalization agent.

## Recommended execution order

1. **Evidence-integrity pass:** fix CSV structure checks, complete numeric parsing,
   finite/unit validation, missingness/qualifier semantics, and independent field
   extraction. Add failing-then-passing regression cases for the examples above.
2. **Review integrity:** separate validation/acceptance states, bind notes and
   decisions to candidate fingerprints, require source-backed corrections, and
   make gold/adjudication outputs immutable and verifiable.
3. **Bounded scientific baseline:** capture the intended PSI-25 source, verify all
   B1-B5 identities, obtain explicit scientific review, and create provenance-rich
   gold fixtures. Keep raw captures local; version suitable fixtures or manifests
   under the repository's evidence policy.
4. **Small normalization-agent pilot:** define a typed proposal contract and a
   deterministic evaluator first. Use a few reviewed examples for development,
   reserve independent cases, log exact requests/responses and run identities,
   and impose token/cost limits before scaling. Include a different investigation
   only through an explicit adapter and source-semantic review.
5. **Archive and retrieval validation:** support per-document associations and
   safe corpus updates, strengthen vector checks, create reviewed retrieval
   questions, and compare keyword/dense/hybrid results reproducibly.
6. **Evidence product:** define reviewed outcome compatibility, condition mismatch
   reporting, and evidence classes; then connect structured matches and document
   context in a scenario explorer. Add grounded synthesis with citation and
   numerical checks after the evidence path is reliable.
7. **Prediction gate:** consider only for a specific reviewed outcome with enough
   comparable observations and an evaluated baseline. It is not a prerequisite
   for the normalization/RAG demonstration.

## Verification and limits

Executed during assessment:

- `python -m pytest -q`: 16 tests pass.
- Ruff formatting/lint, mypy, JavaScript syntax, and local setup diagnostics pass.
- Synthetic probes reproduce CSV evidence loss, numeric interpretation changes,
  insufficient adjudication checks, unverified approved loading, and invalid
  embedding-response acceptance.

The synthetic probe results are stored locally in
`data/review/design-audit/findings.json`; their candidate/decision files are audit
fixtures, not scientific review or gold records. No paid model requests were made.
No application/scientific behavior was modified as part of this assessment.

Passing software checks demonstrate the tested contracts only. They do not
establish NASA mapping accuracy, scientific comparability, or reliable generated
answers. The integrity findings explain where additional contracts/tests are needed.
