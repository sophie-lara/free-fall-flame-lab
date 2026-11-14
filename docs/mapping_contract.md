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

`propose_mapping` is a provider interface and accepts an explicit client. It has
not been added to the pilot batch runner, has not been tested with the live API,
and does not itself implement the batch budget, retry ledger, persistence, or UI
review. Its caller must supply those safeguards before use. The existing pilot
runner still uses the original open-ended `Proposal` response. No automated adapter
to the evidence schema or scientific accuracy scoring is implemented yet.

## Regression and future holdouts

BASS B1, FLEX Table 13 Ar, and Saffire-II 2-2 are prior-reviewed **regression**
examples; their source hashes and pilot outputs are in the pilot plan and existing
results. They have been inspected during development and are not independent tests.

The local `data/processed/holdout-selection-v1.json` identifies new candidate
holdouts BASS B6/B7 and Saffire-II 2-6/2-7, matched to source checksums and record
numbers. They have not been confirmed by a reviewer and are not yet evaluation
references. They need an independent source review and a locked reference before
running the candidate pipeline against them. Table 13's three captured FLEX rows
have already been used; select a different source/table and review it before
claiming an independent FLEX holdout. Keep references out of model requests.
