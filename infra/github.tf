data "github_user" "owner" {
  username = var.github_owner
}

data "github_repository" "this" {
  full_name = "${var.github_owner}/${var.github_repository}"
}

# GitHub Actions deploy identity: OIDC federation, no stored passwords.

resource "azuread_application" "deploy" {
  display_name = "${var.app_name}-github-deploy"
  owners       = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "deploy" {
  client_id = azuread_application.deploy.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

resource "azuread_application_federated_identity_credential" "deploy" {
  application_id = azuread_application.deploy.id
  display_name   = "github-${var.github_repository}-${var.github_branch}"
  description    = "GitHub Actions deploys from ${var.github_owner}/${var.github_repository} on ${var.github_branch}"
  issuer         = "https://token.actions.githubusercontent.com"
  audiences      = ["api://AzureADTokenExchange"]
  # GitHub's OIDC subject includes immutable owner and repository IDs
  # ("repo:<owner>@<owner_id>/<repo>@<repo_id>:ref:..."), so a renamed or recreated
  # repository with the same name cannot reuse this trust.
  subject = "repo:${var.github_owner}@${data.github_user.owner.id}/${var.github_repository}@${data.github_repository.this.repo_id}:ref:refs/heads/${var.github_branch}"
}

resource "azurerm_role_assignment" "deploy" {
  scope                = azurerm_linux_web_app.main.id
  role_definition_name = "Website Contributor"
  principal_id         = azuread_service_principal.deploy.object_id
  principal_type       = "ServicePrincipal"
}

# --- Repository secrets and variables read by .github/workflows/deploy-azure.yml

resource "github_actions_secret" "azure_client_id" {
  repository      = var.github_repository
  secret_name     = "AZURE_CLIENT_ID"
  plaintext_value = azuread_application.deploy.client_id
}

resource "github_actions_secret" "azure_tenant_id" {
  repository      = var.github_repository
  secret_name     = "AZURE_TENANT_ID"
  plaintext_value = data.azurerm_client_config.current.tenant_id
}

resource "github_actions_secret" "azure_subscription_id" {
  repository      = var.github_repository
  secret_name     = "AZURE_SUBSCRIPTION_ID"
  plaintext_value = data.azurerm_client_config.current.subscription_id
}

resource "github_actions_variable" "webapp_name" {
  repository    = var.github_repository
  variable_name = "AZURE_WEBAPP_NAME"
  value         = azurerm_linux_web_app.main.name
}

resource "github_actions_variable" "deploy_approvers" {
  repository    = var.github_repository
  variable_name = "AZURE_DEPLOY_APPROVERS"
  value         = var.deploy_approvers
}
