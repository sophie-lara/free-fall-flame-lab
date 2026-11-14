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

The review workspace loads the BASS candidates from
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
