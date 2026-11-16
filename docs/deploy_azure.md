# Deploying to Azure App Service

Live site: **https://combustion-atlas.azurewebsites.net** (public; admins sign in with GitHub).

## How it is set up

```
Browser ──HTTPS──► App Service front end ──► Easy Auth (GitHub, optional for visitors)
                                              │
                         Web app "combustion-atlas" (Python 3.12, Linux, B1, westeurope)
                           │    FastAPI on Uvicorn: the JSON API and the built React UI
                           ├─ /home/site/wwwroot  code + built UI, deployed by GitHub Actions
                           ├─ /tmp/combustion-atlas  local snapshot of the index (fast reads)
                           ├─ /home/site/data     data, uploaded by scripts/azure_upload_data.sh
                           │    raw/ PDFs + PSI tables · processed/ figures, caches
                           │    embeddings/rag.sqlite3 (passages, vectors, figures, table cards)
                           │    usage/paid-calls.json (site-wide AI answer counter)
                           └─ calls OpenAI (embeddings for questions, gpt-6-luna answers)
```

- **Public UI** at `/`: anyone can ask questions, explore coverage and the evidence
  landscape, and browse sources without signing in.
- **Admins** (`COMBUSTION_ATLAS_ADMINS`, e.g. the GitHub username `sophie-lara`) sign
  in via *Admin sign-in* (`/.auth/login/github`). Admins approve or delete visitor
  uploads and add documents directly; their AI answers are not counted.
- **AI answer limit** for visitors: `COMBUSTION_ATLAS_PAID_DAILY_LIMIT` (100) per UTC
  day and `COMBUSTION_ATLAS_PAID_MIN_INTERVAL_S` (10 s) between answers, site-wide,
  persisted in `/home/site/data/usage`. Over the limit, answers fall back to free
  keyword search. `/api/limits` reports what is left.
- **Visitor uploads** (`public_uploads = true`): anyone can upload a PDF (15 MB, 60
  pages; 3 per person per UTC day, keyed by signed-in name or hashed client IP; each
  upload also uses one site-wide AI call). Uploads are indexed under the reserved
  investigation `VISITOR-UPLOAD`: searchable only by the uploading browser and hidden
  from shared search and corpus counts until an admin approves them on
  the *Add to corpus* page (Approve assigns an investigation ID; Delete removes the
  document, vectors and file). Optional `upload_code` (via `TF_VAR_upload_code`) makes
  visitors enter a code. **Review or approve pending uploads before re-uploading the
  database with `--overwrite`**, which replaces everything on the server.
- `/home` is App Service's persistent network share (like EFS, but included in the
  plan: 1 GB on F1, 10 GB on B1). Code deploys never touch `/home/site/data`.
  SQLite on this share is safe for **one instance only**.
- **Speed:** SQLite reads over the network share are slow, so the app reads from a
  snapshot of the index on local disk (`/tmp/combustion-atlas`, refreshed with SQLite's
  backup API whenever the shared file changes, for example after an upload). Coverage,
  Sources and the evidence landscape are cached in memory and built at startup; stored
  vectors are kept in memory for semantic search; responses are gzipped (except the
  answer stream); hashed front-end assets are cached by browsers for a year.
- Secrets (OpenAI key, GitHub OAuth secret) are app settings, never files.

## Everything is Terraform (`infra/`)

Prerequisites: Azure CLI (`az login`), GitHub CLI (`gh auth login` with repo admin),
Terraform ≥ 1.6, `sqlite3`. Settings live in `infra/terraform.tfvars` (git-ignored);
see `terraform.tfvars.example`. Secrets come from the repo's `.env` at apply time:

```sh
cd infra
export TF_VAR_openai_api_key="$(grep -E '^OPENAI_API_KEY=' ../.env | cut -d= -f2-)"
export TF_VAR_github_oauth_client_secret="$(grep -E '^GITHUB_OAUTH_CLIENT_SECRET=' ../.env | cut -d= -f2-)"
export GITHUB_TOKEN="$(gh auth token)"
terraform plan    # always read the plan first
terraform apply
```

Key variables:

| Variable | Current value | Meaning |
| --- | --- | --- |
| `app_name` | `combustion-atlas` | Web app name → `<app_name>.azurewebsites.net` |
| `plan_name` | `combustion-atlas-nasaspaceapp-plan` | Pins the existing plan so renaming the app never recreates it |
| `location` | `westeurope` | See "Lessons learned" below |
| `app_service_sku` | `B1` | `F1` (free, sleeps, 60 CPU-min/day, 1 GB) or `B1` (always on, ~$13/month) |
| `auth_provider` | `github` | `github` or `microsoft` (Entra ID) |
| `github_oauth_client_id` | GitHub OAuth App client ID | Secret via `TF_VAR_github_oauth_client_secret` |
| `public_access` | `true` | Sign-in optional; admins still checked by the app |
| `allowed_users` | `[]` | With `public_access = false`, the only accounts allowed in (GitHub sign-in admits any account otherwise; Terraform refuses that combination) |
| `admin_emails` | GitHub username / emails | Admin identities |
| `paid_daily_limit`, `paid_min_interval_s` | `100`, `10` | Visitor AI answer limits |
| `public_uploads`, `uploads_per_user_day` | `true`, `3` | Visitor uploads into quarantine |
| `upload_code` | empty | Optional code visitors must enter to upload (`TF_VAR_upload_code`) |

The state file (`infra/terraform.tfstate`) contains secrets in plain text: keep it
local or in a private backend; never commit it.

## Day-to-day operations

**Deploy code** (never automatic): GitHub **Actions → Deploy to Azure → Run workflow**
on `main`, type `deploy`. It checks the approver list, runs lint, types, Python and
front-end tests and the `requirements.txt` lockfile check, builds the React front end
(`frontend/` → `src/combustion_atlas/app/web/`), then deploys with OIDC (no stored
passwords). The start command (`python -m combustion_atlas.app …`) runs Uvicorn.

**Update data** after changing the local index (new documents, figures, table cards):

```sh
scripts/azure_upload_data.sh combustion-atlas combustion-atlas                    # dry run
scripts/azure_upload_data.sh combustion-atlas combustion-atlas --upload --overwrite
```

It uploads only what the app serves (indexed PDFs by SHA-256, PSI tables, referenced
figure crops, the database snapshot with the vectors), stops the app during the
overwrite, and refuses to replace server data without `--overwrite` (documents added
through the hosted *Add to corpus* page live only on the server).
`--bundle out.zip` writes the same package to share without uploading.

**Switch tier** (e.g. B1 for judging, F1 afterwards): change `app_service_sku` and
apply. This is an in-place update of the existing plan, billed per hour.

**Check the site:** `/api/health` (no sign-in), `/api/rag-status` (index counts),
`/api/limits` (AI answers left). Logs: portal → web app → Log stream.

## Lessons learned (read before changing infrastructure)

- **Quota is per region.** This free-trial subscription has 0 App Service quota (F1
  and B1) in most US regions; `westeurope` and `westus3` allow it. Check in the
  portal under *Quotas → App Service* before choosing a region.
- **Plan creation is rate-limited.** A burst of create/delete attempts (including
  failed ones) throttles new plans for a region for hours to ~2 days, and each
  further failed attempt can extend it. Never probe or retry in loops; make one
  attempt, then wait or open a free support request. Updates to an existing plan
  (tier changes) are not affected, which is why `plan_name` is pinned.
- **Microsoft sign-in in the UChicago directory** needs a university admin to approve
  the `profile`/`offline_access` permissions Microsoft adds, so the site uses GitHub
  sign-in instead. Moving back is `auth_provider = "microsoft"` once approved.
- **GitHub OIDC subject** includes immutable IDs
  (`repo:<owner>@<owner_id>/<repo>@<repo_id>:ref:refs/heads/main`); Terraform derives
  them from the GitHub provider.
- **Easy Auth changes** sometimes need a web app restart to take effect
  (`az webapp restart -g combustion-atlas -n combustion-atlas`).
- **Renaming the app** recreates the web app (new disk): re-upload the data, update the
  GitHub OAuth App homepage and callback URL
  (`https://<host>/.auth/login/github/callback`), and run a deploy.

## Costs and cleanup

- B1 ≈ $0.43/day from the $200 free-trial credit; the credit expires 30 days after
  signup. If the subscription is upgraded to pay-as-you-go, switch to F1 or delete the
  app to avoid card charges.
- Set a monthly budget on the OpenAI project: the site's limit caps visitors, but only
  OpenAI enforces spending.
- The storage account used for the shared data download can be deleted when the link
  is no longer needed.
