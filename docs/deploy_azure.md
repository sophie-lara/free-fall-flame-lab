# Deploying to Azure App Service

The app runs on Azure App Service (Linux, Python 3.12) behind Microsoft sign-in.
GitHub deploys **code only, and only when an approved person starts the
"Deploy to Azure" workflow and types `deploy`**. Evidence data (PDFs, figure
crops, PSI experiment tables, the SQLite index) lives on the server's persistent
disk at `/home/site/data` and is uploaded separately.

On Azure the app runs in **public mode**: `/` is the public UI (Ask, Coverage,
Prediction, Sources), and the review workspace is at `/workspace`, visible only to
admins listed in `COMBUSTION_ATLAS_ADMINS`. Admins also get the *Add to corpus* page
and a Public/Workspace switch in the header. Everyone must sign in with an account
you have assigned.

Locally nothing changes: the app listens on `127.0.0.1:8765` in workspace mode
(public UI preview at `/public`) and accepts only loopback requests.

## Quick start (recommended: Terraform)

1. **Tools:** Azure account (Space Apps offer), [Terraform](https://developer.hashicorp.com/terraform/install)
   ≥ 1.6, Azure CLI, GitHub CLI, `sqlite3`.
2. **Sign in:** `az login` (then `az account set -s <subscription-id>`), and
   `gh auth login` with admin rights on the repo.
3. **Configure:** `cd infra && cp terraform.tfvars.example terraform.tfvars`, then
   set `subscription_id`, `location` (e.g. `eastus`), a globally unique `app_name`,
   `admin_emails = ["you@…"]`, and the people allowed in
   (`allowed_user_principal_names`, `guest_emails`). Export the OpenAI key without
   writing it to a file: `read -rs TF_VAR_openai_api_key && export TF_VAR_openai_api_key`.
4. **Create everything:** `terraform init && terraform validate && terraform plan`,
   review the plan, then `terraform apply`. This creates the web app and settings,
   sign-in, the GitHub deploy identity, and the GitHub secrets/variables.
   (This configuration has not been validated against a live subscription yet; fix
   any `validate`/`plan` errors before applying.)
5. **Upload the data:** from the repo root, `scripts/azure_upload_data.sh <app_name> <resource_group>`
   (dry run, ~210 MB), then again with `--upload`.
6. **Deploy the code:** push your commits, then on GitHub **Actions → Deploy to
   Azure → Run workflow** on `main` and type `deploy`. It runs the tests first.
7. **Check:** open `https://<app_name>.azurewebsites.net` in a private window. You
   should be asked to sign in; after signing in as an admin you should see the
   switch, the corpus counts on the home page, and `/api/me` should report
   `"is_admin": true`.

Details for each part are in [`infra/README.md`](../infra/README.md). The manual
portal steps below do the same thing by hand and remain the reference.

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
| `COMBUSTION_ATLAS_UI` | `public` (public UI at `/`, workspace at `/workspace` for admins) |
| `COMBUSTION_ATLAS_ADMINS` | your sign-in email(s), comma-separated; only these can upload or open the workspace |
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

The package (~210 MB) holds `data/raw` (indexed PDFs, PSI tables and documents, NTRS papers), `data/processed/{rag,visuals}`,
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
