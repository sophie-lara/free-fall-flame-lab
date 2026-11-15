# Mapping proposal contract

`ingestion.mapping_contract` defines a separate versioned Pydantic response
contract. `rag.visual_models.VisualArtifact` and `TableContent` remain the source
table contract; `SourceBatch` provides source-cell references into this mapping
step. Neither a mapping proposal nor a JSON-schema-valid result is a reviewed
`EvidenceCandidate` or an `ExperimentRecord`.

The mapping request includes source cells and context, a profile-specific list of
allowed fields, and the structured output schema. `unmapped` is available for
uncertain concepts. Each proposed field links to source-cell indexes and retains
the value, unit, qualifier, missingness and mapping status. The validator checks
profile vocabulary, references, source markers and the reviewed-source scope of
FLEX `d` and `k`; those two mappings remain proposed. The raw source snapshot
must be saved along with proposals. Field absence without a cell does not currently
have an output entry: `not_found_in_source` requires a separate source-scope and
coverage mechanism, not a fabricated cell reference.

`propose_mapping` is a provider interface and accepts an explicit client. The
separate `ingestion.mapping_runner` connects it to the three-row regression with
the same model, per-run $2 reservation policy, no automatic retries, source hash
checks, new output directory and usage ledger. It has not yet been tested with the
live API. The original pilot runner still uses the original open-ended `Proposal`
response. No automated adapter to the evidence schema or scientific accuracy
scoring is implemented yet. The reservation is an estimate under assumed rates,
not a provider-enforced spending cap; other runs are outside its scope.

Preview the three-row scope without model calls:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.ingestion.mapping_runner --plan data/processed/pilot-plan-v1.json --output data/processed/mapping-regression-v1
```

The explicit `--allow-provider-calls` flag enables the live requests. Review the
configuration and account limits before use. The model request includes the FLEX
source pages but excludes the new holdout rows and human review notes.

## Regression and future holdouts

BASS B1, FLEX Table 13 Ar, and Saffire-II 2-2 are prior-reviewed **regression**
examples; their source hashes and pilot outputs are in the pilot plan and existing
results. They have been inspected during development and are not independent tests.

The local `data/processed/holdout-selection-v1.json` identifies new candidate
holdouts BASS B6/B7 and Saffire-II 2-6/2-7, matched to source checksums and record
numbers. Source-bound draft reviews are captured in `data/processed/holdout-reviews-v1.json`;
this snapshot retains open questions and is not automatic scientific approval.
Table 13's three captured FLEX rows
have already been used; select a different source/table and review it before
claiming an independent FLEX holdout. Keep references out of model requests.

The review tooling loads the BASS candidates from
`data/review/additional-candidates/holdout-bass.json` and the source-faithful Saffire
strings from `data/review/holdout-evidence.json`. The latter deliberately retains
compound and ambiguous cells as strings rather than inventing numeric conversions.
Notes bind to candidate fingerprints and remain draft review records; the snapshot
preserves them for evaluation without treating open interpretations as resolved.

The completed three-row regression is stored in `data/processed/mapping-regression-v1`.
`data/processed/mapping-regression-recheck-v1.json` reapplies current local rules
without rewriting provider responses. The first regression produced no model
geometry field for B1; the deterministic BASS extractor supplies film and the
coverage check flags that omission. The Saffire `?-g` column retains its ambiguity.

## Four-row holdout evaluation

The holdout runner uses the four source rows and the controlled mapping contract.
Before preparing a request, it rechecks the saved review snapshot against current
source bytes, original cells, candidate fingerprints and saved notes. The request
contains only source cells, profile and instructions, never review decisions or
expected answers. The saved result records the reference snapshot hash, not its
contents. B6/B7 use BASS and 2-6/2-7 use Saffire profiles; none is sent as a FLEX
example. Saffire 2-7's reviewed interpretation remains unresolved.

Preview without calling a provider:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.ingestion.holdout_runner --output data/processed/holdout-evaluation-v1
```

Only add `--allow-provider-calls` for an authorized live run. The runner uses
`gpt-6-luna`, the same $2 per-run estimated reservation and the same no-retry,
new-directory ledger. This is not a provider-enforced cap. Check actual provider
spending and pricing separately. After all four results are saved, create a local
manual comparison with:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.ingestion.holdout_compare --reference data/processed/holdout-reviews-v1.json --results data/processed/holdout-evaluation-v1 --output data/processed/holdout-comparison-v1.json
```

The comparison verifies reference and source hashes and retains the original
review notes. It does not grade accuracy or promote records. The independent FLEX
candidate is Table 2's He row in `data/review/flex-table2-candidates.json`; it is
an unreviewed background-study entry, not a FLEX flight run. It is not part of the
four-row evaluation runner.

## Bounded CSV batches

`ingestion.csv_batch_runner` accepts explicitly selected CSV record numbers from
the project's `data/raw`, in groups of at most 11. It supports the BASS-II B-series
and Saffire-II `2-*` experiment identities and rejects unsupported rows, including
documentation rows. It does not silently turn them into experiments. Example dry run:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.ingestion.csv_batch_runner --csv 'data/raw/preserved-review/PSI-25_Experimental table_BASS-II.csv' --investigation PSI-25 --records 9 10 11 --output data/processed/bass-batch-preview
```

The `--allow-provider-calls` flag explicitly sends the selected rows; the $2
reservation is per run, not a cumulative account cap. Source references, model
outputs and local checks are saved in a new output directory. The runner refuses
to resume or overwrite it after an interrupted request. Inspect its ledger and
provider usage before planning any retry. Outputs remain unreviewed JSON and are
not automatically integrated into the review UI or approved search.

To make a completed BASS batch available for manual review, use the explicit
source-checking adapter:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.review.model_candidates --results data/processed/bass-b8-b10-v1 --output data/review/model-candidates/bass-b8-b10-v1.json
```

It verifies the file hash, row identity and all raw cells, preserves model notes,
flags and original result hashes, and creates unreviewed evidence candidates.
It refuses duplicate candidate identities and won't overwrite an existing file.
The review tooling loads these candidates and binds saved notes to their
fingerprints. New `model-review-candidates-v2` envelopes also preserve each model
field's complete source-cell links, mapping status, missingness, qualifier and
source context in a sidecar. Older candidate envelopes require the original result
files for those details. Its output is not an approved `CandidateBatch`; the existing
`review apply` workflow requires a separate source- and decision-bound adapter.
No model proposal or draft review note is automatically promoted to approved search.

The four-row evaluation exposed B6's unnamed 2 cm dimension, B7's omitted film
geometry, Saffire 2-6's `037`, and Saffire 2-7's qualified `n/a` and compound
values. Current checks flag those cases without changing the source strings.
`data/processed/holdout-evaluation-recheck-v3.json` applies those changes to saved
responses without new provider calls; its flags do not prove full accuracy.

## Full CSV run preparation

`ingestion.full_csv_run` prepares a source-bound plan for the BASS-II B/F/M/O/P/T
series (including letter suffixes) and Saffire-II sample rows. Existing review
candidates are excluded only when they match the source hash; incompatible
identities stop planning. Saffire non-run rows are listed as exclusions, and numbered
source-note rows are also included as source-linked context on its experiment requests.

The plan freezes source hashes, selected record numbers, request hashes, code and
package versions, model and a cumulative estimated reservation. It defaults to a
$2 total reservation under the documented assumed prices. This is **not** a provider
billing cap and does not count other API use. No requests are sent by planning or
the default run command.

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.ingestion.full_csv_run plan --bass 'data/raw/preserved-review/PSI-25_Experimental table_BASS-II.csv' --saffire 'data/raw/preserved-review/PSI-99_Experimental table_SAFFIRE-2.csv' --budget 2 --output data/processed/full-csv-plan-v3.json
.\.venv\Scripts\python.exe -m combustion_atlas.ingestion.full_csv_run run --plan data/processed/full-csv-plan-v3.json --output data/processed/full-runs/nasa-csv-v1
```

Only an explicitly authorized run adds `--allow-provider-calls`. It creates a
run ledger, reserves each request before sending, and writes source-linked outputs.
The growing `review-report.md` groups flagged results and picks a reproducible
audit sample of unflagged rows; `review-index.json` supports selective UI import.
A clean automated check does not constitute approval. The global instrument-setting
interpretation caveat is retained in the report rather than repeated for every row.

`--resume` skips checksum-verified completed responses from the exact plan. A
reserved but incomplete request stops the run: inspect provider usage and the
ledger before deciding how to handle it; there is no automatic retry. If a process
is killed, its `.run-lock` may remain and must not be removed until the process and
ledger have been checked. Changing the source, mapping code or version invalidates
the plan; make a new one. Import only after the run is complete:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.review.model_candidates --results data/processed/full-runs/nasa-csv-v1 --review-index data/processed/full-runs/nasa-csv-v1/review-index.json --output data/review/model-candidates/full-csv-review-v1.json
```

Only flagged rows and the suggested audit sample are imported. Candidates and
notes are still unreviewed and do not enter approved search automatically; the
source- and review-bound adjudication bridge remains outstanding. Table and page
document ingestion are outside this CSV-specific run.
