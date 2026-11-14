# Local review workspace

Start from the repository root:

```powershell
.\.venv\Scripts\python.exe -m combustion_atlas.app --port 8766
```

Open [the workspace](http://127.0.0.1:8766/#overview),
[experiment review](http://127.0.0.1:8766/#experiments),
[document search](http://127.0.0.1:8766/#search), or
[source library](http://127.0.0.1:8766/#sources).
The default port is 8765 when `--port` is omitted. Keep the terminal running;
Ctrl+C stops the server. No frontend build or model API call is needed.

## Candidate review

The workspace reads `CandidateBatch` artifacts from
`data/review/*-b1-b5.json` and `data/review/additional-candidates/*.json`.
Use the normalization command in [operations.md](operations.md) to generate a
batch. Each investigation/test identity must be unique across loaded batches.
The UI displays empty states when the workspace contains no data artifacts.

Select a candidate and inspect Conditions, Measured outcomes, Instrument settings,
and Original cells. Fields come from the native `ExperimentRecord` schema:
scalar condition labels, dimension/measurement dictionaries, outcomes, validation
messages, and raw source cells retain their separate meanings. Source filenames,
record/column references, source locators, and checksums remain visible.

Condition filters match exact labels after case/whitespace normalization.
Numerical ranges are inclusive and require the canonical units `%`, `kPa`, and
`cm/s`. Missing measurements and instrument controls cannot satisfy those ranges.
Filters do not establish scientific comparability.

Enter your reviewer name, assessment, finding, and supporting source reference,
then select **Save review note**. Notes append to
`data/review/human-notes.jsonl` and reappear when the workspace reloads. Unsaved
form entries survive changes between records/tabs within the current page session;
save before reloading or closing the page. The reviewer name is remembered locally
by the browser. Notes are drafts; candidate values and validation states stay
unchanged. Use the review CLI for fingerprinted adjudication and gold export.

## Documents and sources

Document search uses the existing SQLite FTS5 index at
`data/embeddings/rag.sqlite3`. Results preserve chunk identifiers, source checksums,
and physical PDF pages. This browser route runs keyword retrieval without calling
an embedding or answer provider. Use the provider/RAG CLI for API-backed retrieval.

The source library is derived from candidate source identities and indexed pages.
Captured files can be opened only when matching bytes are found inside this
workspace's `data/raw` directory. Files are checked against their source checksum;
external paths, missing files, and modified captures are not served. Indexed
sources without a matching local capture retain their source links.

## Local API

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Server readiness |
| `GET /api/overview` | Actual candidate, source, page, and chunk counts |
| `GET /api/experiments` | Native records, source metadata, mapping decisions, and notes |
| `GET /api/structured-search` | Candidate condition filters |
| `GET /api/sources` | Captured/indexed source metadata |
| `GET /api/search?q=...&investigation=...&k=5` | Keyword results with native chunk citations |
| `GET /api/documents/{source_id}` | Checksum-verified file within `data/raw` |
| `POST /api/reviews` | Validated draft note for an existing candidate |
| `POST /api/review-notes` | Alias for draft-note submission |

Review writes require bounded JSON, nonblank review fields, an existing candidate,
and a same-origin local request. The interface is a loopback development workspace,
not a multi-user deployment.
