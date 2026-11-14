# Azure infrastructure (Terraform)

Provisions everything in [`docs/deploy_azure.md`](../docs/deploy_azure.md) steps 1–4:
resource group, Linux App Service plan and web app (Python 3.12, one instance),
app settings, Microsoft sign-in restricted to assigned users, the GitHub OIDC
deploy identity, and the GitHub Actions secrets/variables the deploy workflow reads.
Evidence data (step 5) is still uploaded with `scripts/azure_upload_data.sh`.

## Prerequisites

- An Azure subscription, and permission to create app registrations and invite
  guests in its Entra tenant.
- Azure CLI: `az login` (and `az account set -s <subscription>`).
- GitHub access with **admin** rights on the repository, to write Actions secrets
  and variables: `gh auth login`, or `export GITHUB_TOKEN=...` (a token with repo
  admin). If the provider does not pick up the `gh` login, run
  `export GITHUB_TOKEN="$(gh auth token)"`.
- Terraform >= 1.6.

## Configure

```sh
cd infra
cp terraform.tfvars.example terraform.tfvars   # ignored by git; fill in
```

Required: `subscription_id`, `location`, `app_name` (globally unique; the host is
`<app_name>.azurewebsites.net`), and the OpenAI key. Usually also
`admin_emails`, `allowed_user_principal_names` and `guest_emails`.

Pass the OpenAI key through the environment so it never lands in a file you could
commit:

```sh
read -rs TF_VAR_openai_api_key && export TF_VAR_openai_api_key
```

Set a monthly budget on the OpenAI project too: sign-in limits who can use the
app, not how much they spend.

## State contains secrets

The Terraform state holds the OpenAI key and the sign-in client secret in plain
text. Keep it local (`*.tfstate*` is git-ignored here) or move it to a private
backend such as an Azure Storage container with restricted access. Never commit
state or `terraform.tfvars`. Do commit `.terraform.lock.hcl`.

## Apply

```sh
terraform init
terraform plan
terraform apply
terraform output next_steps
```

Then upload the evidence data (dry run first):

```sh
scripts/azure_upload_data.sh <app_name> <resource_group>
scripts/azure_upload_data.sh <app_name> <resource_group> --upload
```

Deploy code from GitHub: **Actions → Deploy to Azure → Run workflow** on `main`,
type `deploy`.

## Deploy identity: no stored passwords

GitHub Actions signs in through OIDC: a federated credential trusts tokens for
`repo:<owner>/<repo>:ref:refs/heads/<branch>` only, and its service principal has
**Website Contributor** on this one web app and nothing else. There is no client
secret or publish profile to leak; FTP and Web Deploy basic auth are disabled.
`AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID` are identifiers,
stored as secrets only to match the workflow.

## Add or remove users

Sign-in requires an assignment on the enterprise application.

- People already in your tenant: edit `allowed_user_principal_names`.
- Outsiders: edit `guest_emails`. Terraform sends a guest invitation and assigns
  the guest; they sign in with their own Microsoft account, work/school email, or a
  one-time code.

Then run `terraform apply`. Removing an entry removes the assignment (they can no
longer sign in); removing a guest email also deletes that guest user from the
tenant. Admins (`admin_emails`) are a separate app setting and must also be
allowed users.

## Notes

- The sign-in client secret expires after two years. Rotate with
  `terraform apply -replace=azuread_application_password.signin`.
- Keep the plan at one instance: SQLite on the shared disk is not safe across
  instances.
- Custom domains: add them to `COMBUSTION_ATLAS_ALLOWED_HOSTS` and to the sign-in
  app's redirect URIs in `main.tf` / `signin.tf`.
- If GitHub deploys move to an Environment, change the federated credential
  subject in `github.tf` to `repo:<owner>/<repo>:environment:production`.
