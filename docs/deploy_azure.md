# Deploying to Azure App Service

The app runs on Azure App Service (Linux, Python 3.12) behind Microsoft sign-in.
GitHub deploys **code only, and only when an approved person starts the
"Deploy to Azure" workflow and types `deploy`**. Evidence data (PDFs, figure
crops, the SQLite index) lives on the server's persistent disk at
`/home/site/data` and is uploaded separately.

Locally nothing changes: the app still listens on `127.0.0.1:8765` and accepts
only loopback requests unless the hosting settings below are given.

## 1. Create the web app (portal, once)

1. Create a resource group, e.g. `combustion-atlas`.
2. Create a **Web App**: Publish *Code*, Runtime *Python 3.12*, OS *Linux*, a Basic
   plan (check current pricing). Note the name; the host is `<name>.azurewebsites.net`.
3. Keep the app at **one instance**. SQLite on the shared disk is fine for a small
   team but is not safe across multiple instances.

## 2. Configure the app

**Settings → Environment variables → App settings**

| Name | Value |
| --- | --- |
| `OPENAI_API_KEY` | the API key (or a Key Vault reference) |
| `COMBUSTION_ATLAS_EMBEDDING_PROVIDER` | `openai` |
| `COMBUSTION_ATLAS_EMBEDDING_MODEL` | `text-embedding-3-small` (must match the uploaded index) |
| `COMBUSTION_ATLAS_ANSWER_PROVIDER` | `openai` |
| `COMBUSTION_ATLAS_ANSWER_MODEL` | e.g. `gpt-6-luna` |
| `COMBUSTION_ATLAS_ALLOWED_HOSTS` | `<name>.azurewebsites.net` (comma-separate custom domains) |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` (installs `requirements.txt` on deploy) |

Copy any other `COMBUSTION_ATLAS_*` values from your local `.env`. Never commit
the key. Also set a monthly budget on the OpenAI project: Azure sign-in limits who
can use the app, not how much they spend.

**Settings → Configuration → Startup command**

```sh
python -m combustion_atlas.app --host 0.0.0.0 --port 8000 --workspace /home/site/data
```

The app refuses to listen on `0.0.0.0` unless `COMBUSTION_ATLAS_ALLOWED_HOSTS` is
set, and still rejects requests for any other host name.

## 3. Require Microsoft sign-in

1. **Settings → Authentication → Add identity provider → Microsoft**, workforce
   tenant, create a new app registration. Restrict access: *Require authentication*;
   unauthenticated requests: *HTTP 302 redirect*.
2. **Microsoft Entra ID → Enterprise applications →** the app's registration →
   *Properties*: set **Assignment required = Yes**. Then *Users and groups*: add the
   people allowed in. Without this, any account in the tenant can sign in.
3. Outsiders (teammates on other accounts, judges): **Entra ID → Users → Invite
   external user**, then assign them as above. They sign in with their own Microsoft
   account, work/school email, or an emailed one-time code.

## 4. Connect GitHub (approval-gated deploys)

1. **Entra ID → App registrations → New registration** (e.g. `github-deploy-atlas`).
   Under *Certificates & secrets → Federated credentials → Add*: scenario *GitHub
   Actions*, organization `sophie-lara`, repository `free-fall-flame-lab`, entity
   *Branch*, branch `main`. No client secret is needed (OIDC).
2. On the **web app → Access control (IAM) → Add role assignment**: role *Website
   Contributor*, assigned to that app registration, scoped to this web app only.
3. GitHub repo **Settings → Secrets and variables → Actions**:
   - Secrets: `AZURE_CLIENT_ID` (the registration's application ID),
     `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`.
   - Variables: `AZURE_WEBAPP_NAME` = the web app name; optional
     `AZURE_DEPLOY_APPROVERS` = comma-separated GitHub usernames (default
     `sophie-lara`).

To deploy: **Actions → Deploy to Azure → Run workflow** on `main`, type `deploy`.
The workflow checks you are an approved deployer, runs lint, type checks, tests and
the `requirements.txt` lockfile check, then deploys. Pushing to `main` alone never
deploys. Regenerate `requirements.txt` after dependency changes:

```sh
uv export --no-dev --no-hashes --no-editable --no-header --format requirements-txt --frozen -o requirements.txt
```

GitHub's approval-button protection (Environments with required reviewers) is not
available for private repositories on personal plans. With GitHub Enterprise or a
public repository, add `environment: production` to the deploy job, set required
reviewers on that environment, and change the federated credential entity to
*Environment* `production`.

## 5. Upload the evidence data (once, or deliberately)

Requires the Azure CLI (`az login`) and `sqlite3`.

```sh
scripts/azure_upload_data.sh <name> <resource-group>                      # dry run: lists contents
scripts/azure_upload_data.sh <name> <resource-group> --upload             # first upload
scripts/azure_upload_data.sh <name> <resource-group> --upload --overwrite # replace server data
```

The package (~80 MB) holds `data/raw`, `data/processed/{rag,visuals}`,
`data/review` and a consistent SQLite snapshot. It never includes `.env`, backups
or evaluation outputs. Because documents uploaded through the hosted app are stored
on the server, the script refuses to replace an existing server index without
`--overwrite`, and stops the app while replacing it.

Code deploys never touch `/home/site/data`.

## Checks after deploying

- Open `https://<name>.azurewebsites.net` in a private window: you should be sent
  to Microsoft sign-in, and an unassigned account should be refused.
- After signing in, the Corpus page should show the uploaded documents, and
  `/api/rag-status` should report matching indexed and embedded counts.
- Logs: **Monitoring → Log stream**.
