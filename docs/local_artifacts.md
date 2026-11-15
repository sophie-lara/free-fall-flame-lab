# Local artifacts not in Git (as of 2026-11-15)

Everything below lives only on Sophie's machine (Git-ignored) and, for the app's data,
on the Azure web app's disk at `/home/site/data`. Sizes are approximate.

## Corpus and index (what the app searches)

| Path | What it is | Size | How it was made |
| --- | --- | --- | --- |
| `data/embeddings/rag.sqlite3` | The index: 1,546 passages from 29 documents, their `text-embedding-3-small` vectors, 392 figure descriptions, 97 reviewed table record cards | 22 MB | `rag add` per PDF, `providers embed --missing-only`, `rag.visuals index`/`embed`, `analysis.evidence_bridge sync` |
| `data/raw/bass-ii-summary.pdf` | BASS-II summary report (NASA/TM-20210011385) | 47 MB | NTRS |
| `data/raw/psi/` | PSI downloads for BASS, BASS-II, FLEX, FLEX-2, Saffire I–III, SAME, SAME-R: experiment-table CSVs and text PDFs, plus `manifest.jsonl` (file, SHA-256, PSI page) | 112 MB | `ingestion.psi_batch --download` |
| `data/raw/ntrs/` | 13 NTRS papers/reports (6 BASS-II, 3 FLEX incl. the 314-page FLEX results TP, 4 Saffire), plus `manifest.jsonl` | 75 MB | `ingestion.ntrs <ids> --download` |
| `data/processed/visuals/*.png` | 392 full-page figure crops (hash-bound to the descriptions) | ~100 MB | `rag.visuals extract` |
| `data/processed/visuals/*.jsonl` | Figure capture manifests and `gpt-6-luna` descriptions (prompt v2) | 1.9 MB | `rag.visuals describe` |
| `data/processed/rag/` | Per-source page/chunk JSONL, evidence landscape (`landscape.json`) | 3 MB | `rag add`, Explore → Evidence landscape |

Indexed documents by investigation: BASS-II (PSI-25) report + SRD + 6 NTRS papers;
BASS (PSI-26) 9 docs (engineering drawings and SPICE/SLICE files skipped);
FLEX (PSI-69) 3 NTRS; Saffire (PSI-98/100 + `SAFFIRE`) 4 NTRS + 5 PSI files.
SAME/SAME-R and FLEX-2 PDFs were downloaded but not indexed. PSI returned 404 for
7 files, including `PSI-26_Reports_BASS_FinalReport.pdf`.

## Evaluation and review drafts

| Path | What it is | Size |
| --- | --- | --- |
| `data/review/evaluation/bass-ii-questions.draft.json` | 15 draft evaluation questions (10 dev, 5 held-out), unreviewed | 12 KB |
| `data/processed/eval/` | Draft evaluation reports and the POC validation notes | 300 KB |

## Never share these (secrets or machine-specific)

| Path | Why |
| --- | --- |
| `.env` | OpenAI key, GitHub OAuth client secret |
| `infra/terraform.tfvars` | Deployment settings (subscription ID, admin identities) |
| `infra/terraform.tfstate*` | Terraform state: contains the OpenAI key and the sign-in secret in plain text |
| `data/backups/` | Database snapshots taken before each change (42 MB) |

## How to get the corpus without regenerating it

1. **Just look:** the deployed app shows the documents (Sources, Corpus), cited
   answers, figures and coverage. No files needed.
2. **Download a copy:** Sophie can share a bundle (the same ~240 MB package
   `scripts/azure_upload_data.sh` builds) via a time-limited link or a shared drive.
   Unzip it into `data/` and the app works with no API calls.
3. **Rebuild it:** every step is scripted (commands above). Costs roughly $0.25 of
   OpenAI calls (figure descriptions; embeddings are a fraction of a cent) and about an
   hour, mostly the 286 FLEX figure descriptions. Model outputs will differ slightly.
