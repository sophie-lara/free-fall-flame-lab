# Reviewed evidence artifacts

Prepare the local artifacts from the saved reconciliation and source captures:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.review.fixtures
```

The command checks candidate fingerprints against the confirming notes, verifies
that the notes exist in the saved review log, and checks each captured source's
SHA-256. It validates the original and reviewed records with the versioned
`EvidenceCandidate` schema, then writes:

- `data/processed/reviewed-evidence-v1.json`: original and reviewed candidates,
  record type, source identifiers, complete note history, corrections, and open
  questions.
- `data/processed/reviewed-decisions-v1.json`: source-bound decisions, reviewer,
  confirmation timestamp, references, original/reviewed fingerprints, open
  questions, and the SHA-256 of the exact evidence artifact bytes.

Both files are local and Git-ignored. The command refuses to replace differing
outputs. It makes no model requests and does not modify candidate files or notes.

The decision file records six acceptances, two corrections, and three cases that
need research. B2's extraction acceptance is preserved in the review history;
its final oxygen interpretation remains open. B3/B5's supported dimensions are
added independently; missing material/geometry are not inferred. B4's reported
negative CO and Saffire-II 2-4's `037 mm` remain source-faithful and unresolved.
The three FLEX entries are background-study table rows, rather than individual
flight runs. `n/a` is kept as a source marker whose meaning needs documentation;
the original candidate and its original qualifier are retained unchanged.

`reviewed-evidence-v1` is a separate mixed-format evidence schema. The existing
`ExperimentRecord` and `review apply`/approved-search CLI use a different run-level
schema; these files are not directly accepted by that CLI. An explicit adapter
and evaluation policy are required before using the records in that workflow.
The review actions capture transcription decisions and open questions, not a
scientific comparability policy or a claim that every value is ready for modeling.

Regression tests use synthetic source-shaped cases to verify corrections,
provenance, note binding, changed-source rejection, exact output-byte hashes,
and immutable output handling. Before a pilot, discuss the provider, budget,
data sent to it, saved outputs, and independent held-out evaluation split.
