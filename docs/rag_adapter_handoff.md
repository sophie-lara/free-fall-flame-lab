# Evidence-to-RAG adapter handoff

## Purpose and division

The ingestion path produces source-bound candidate evidence, human review notes,
and reviewed snapshots. The RAG-side adapter should turn eligible evidence into
record cards and coverage/search records, while preserving original values,
review state, open questions, and source references. Numeric retrieval should use
reviewed structured evidence; document retrieval supplies context. An answer using
both should label the evidence for each claim.

## Inputs available locally

- `data/processed/reviewed-evidence-v1.json`: versioned mixed-format reviewed
  evidence, with `records[]` containing `evidence_kind`, `source_sha256`, original
  and reviewed candidates, review history, transformations, and open questions.
- `data/processed/reviewed-decisions-v1.json`: source-bound decisions. Its
  `fixture_sha256` hashes the exact bytes of the evidence file. Verify this before
  accepting the pair; individual records carry candidate and reviewed fingerprints.
- `data/processed/holdout-reviews-v1.json`: four source-bound review snapshots,
  including the reviewer's notes and unresolved Saffire 2-7 interpretation. These
  are draft review references, not automatically approved scientific facts.
- `data/review/model-candidates/*.json`: review UI candidates generated from model
  results. They are unreviewed, with original result-file hashes; review notes are
  stored separately in `data/review/human-notes.jsonl` and bound by candidate
  fingerprint. A note alone does not automatically promote a record.
  New `model-review-candidates-v2` envelopes additionally contain a `model_results`
  sidecar keyed by identity: each field retains the full model mapping, independent
  missingness/qualifier, all linked source cells, and original source context. Older
  envelopes do not contain this sidecar; use their original result files and hashes.
- `data/processed/full-runs/<run>/row-NNNN/01.json`: eventual unreviewed mapping
  proposals, source cells and context, model/usage metadata, and validation issues.
  Each `review-report.md` and `review-index.json` is a triage aid, not an approval.

These data artifacts are local and Git-ignored. Share the matching artifacts and
source captures via the team's chosen shared location; no upload is performed by
this document. File names alone do not establish identity: verify hashes.

## Current evidence contract

`src/combustion_atlas/review/evidence_schema.py` defines `EvidenceCandidate`.
Identity is investigation/test/sample; each `EvidenceValue` has `value`, `unit`,
qualifier/uncertainty, original value/unit, and `EvidenceLocation`. Raw cells are
also retained. Location includes source URL, filename, source SHA-256, CSV/table row,
column, optional physical PDF page and table label, and a synthetic-data flag.
Review issues and status must accompany the candidate. Preserve unresolved values
and source markers; an accepted transcription can still contain unresolved science.

The native `ExperimentRecord` and `review apply` workflow are different contracts.
The reviewed-evidence artifact is not directly accepted there. The bridge must
reject or explicitly report representations it cannot faithfully convert, including
qualitative values, multiple source cells, and unresolved source markers. Do not
coerce them to zero, fabricate numeric values, or silently drop qualifiers.
In particular, `EvidenceValue` currently has one location and one free-text
qualifier: a value with multiple linked cells or with both a missingness marker and
a separate qualifier requires its sidecar/original response to remain attached.

## Source locator conventions

- For a CSV, preserve exact filename/source hash, one-based CSV **record** number
  including its header as record 1, and original column. Record numbers are not
  necessarily physical line numbers when cells contain newlines. Page/table are
  null unless a separately verified association exists; do not invent a PDF ID.
- For a PDF table with a corresponding RAG `VisualArtifact`, refer to its real
  `artifact_id` and preserve the full source hash, physical page, table label and
  row/column location. The agreed proposed ID convention is
  `<source_id>:p<physical_page>:table:<label>`, where `source_id` is the first 16
  hex characters of the document SHA-256. Verify the actual artifact and bytes;
  a source table label alone is not proof an artifact exists. Physical PDF pages
  are one-based; `TableCell` grid coordinates are zero-based.
- Current `EvidenceLocation.table` contains a source label such as `13`, not a
  guaranteed RAG artifact ID. Its `row` convention for reviewed FLEX records is a
  one-based data-row label, not necessarily a `TableCell` grid coordinate. An
  explicit verified crosswalk is needed before treating them as interchangeable.
- FLEX Table 13 entries are background-study rows, not individual flight runs.
  Do not join or classify them as flight observations without evidence.

## Record-card and retrieval requirements

Cards should contain exact source cell text for quotations, plus independently
identified normalized or derived values, units, qualifiers, review status, open
questions, and source locations. A quote-in-passage check verifies an exact excerpt,
not that its mapping or scientific interpretation is correct. Keep derived values
distinguishable from source text. Surface potentially conflicting values alongside
both citations and check units, conditions, and identity before declaring a conflict.

Use the currently reviewed BASS, Saffire and FLEX records as integration fixtures.
Test CSV locators without fabricated pages, PDF crosswalks, unresolved B2/B4 and
Saffire 2-4 values, source `n/a`, background-row type, rejected/unreviewed records,
changed-source and changed-decision hashes, and any loss in conversions. Evaluate
structured, contextual and mixed questions separately against the draft table
questions; a schema-valid or indexed card is not automatically reviewed or true.

## Follow-up responsibilities

Ingestion maintains source captures, mapping proposals, review records and decisions.
The RAG-side adapter owns record-card/coverage conversion and retrieval integration.
Together, establish a source- and decision-bound promotion policy, field-level
provenance crosswalks and shared artifact transport before treating new full-run
proposals as reviewed evidence. The prepared CSV run can proceed independently;
its outputs must not be promoted solely because they were processed.
