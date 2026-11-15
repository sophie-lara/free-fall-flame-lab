data "azurerm_client_config" "current" {}
data "azuread_client_config" "current" {}

locals {
  # Built from the variable, not the web app resource, to avoid a dependency
  # cycle (the web app needs the sign-in app's client ID).
  app_host = "${var.app_name}.azurewebsites.net"
  # The app reads <workspace>/data/..., and the data lives in /home/site/data.
  workspace = "/home/site"
  # Pinned separately so renaming the app never recreates the plan (plan creation
  # is rate-limited by Azure on this subscription).
  plan_name = var.plan_name != "" ? var.plan_name : "${var.app_name}-plan"

  # Default access role for apps without app roles.
  default_app_role_id = "00000000-0000-0000-0000-000000000000"

  # Free/Shared tiers (F1, D1) do not support always-on; the app sleeps when idle.
  always_on = !contains(["F1", "D1"], upper(var.app_service_sku))

  use_github = var.auth_provider == "github"
}

# --- Hosting -------------------------------------------------------------

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
}

resource "azurerm_service_plan" "main" {
  name                = local.plan_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = var.app_service_sku
  # SQLite on the shared disk is not safe across instances.
  worker_count = 1
}

resource "azurerm_linux_web_app" "main" {
  lifecycle {
    precondition {
      condition = !local.use_github || (
        var.github_oauth_client_id != "" && var.github_oauth_client_secret != "" &&
        (var.public_access || length(var.allowed_users) > 0)
      )
      error_message = "GitHub sign-in needs github_oauth_client_id, TF_VAR_github_oauth_client_secret, and either public_access or a non-empty allowed_users (it admits any GitHub account otherwise)."
    }
  }

  name                = var.app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  # Deploys and data uploads use Entra tokens (OIDC / az login), not publish passwords.
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false

  site_config {
    always_on           = local.always_on
    ftps_state          = "Disabled"
    minimum_tls_version = "1.2"
    worker_count        = 1
    app_command_line    = "python -m combustion_atlas.app --host 0.0.0.0 --port 8000 --workspace ${local.workspace}"

    application_stack {
      python_version = "3.12"
    }
  }

  app_settings = merge({
    OPENAI_API_KEY                           = var.openai_api_key
    COMBUSTION_ATLAS_EMBEDDING_PROVIDER      = "openai"
    COMBUSTION_ATLAS_EMBEDDING_MODEL         = var.embedding_model
    COMBUSTION_ATLAS_ANSWER_PROVIDER         = "openai"
    COMBUSTION_ATLAS_ANSWER_MODEL            = var.answer_model
    COMBUSTION_ATLAS_ALLOWED_HOSTS           = local.app_host
    COMBUSTION_ATLAS_ADMINS                  = join(",", var.admin_emails)
    COMBUSTION_ATLAS_WORKSPACE               = local.workspace
    SCM_DO_BUILD_DURING_DEPLOYMENT           = "true"
    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = azuread_application_password.signin.value
    GITHUB_PROVIDER_AUTHENTICATION_SECRET    = var.github_oauth_client_secret
    COMBUSTION_ATLAS_ALLOWED_USERS           = join(",", var.allowed_users)
    COMBUSTION_ATLAS_PAID_DAILY_LIMIT        = tostring(var.paid_daily_limit)
    COMBUSTION_ATLAS_PAID_MIN_INTERVAL_S     = tostring(var.paid_min_interval_s)
    COMBUSTION_ATLAS_PUBLIC_UPLOADS          = var.public_uploads ? "1" : "0"
    COMBUSTION_ATLAS_UPLOAD_CODE             = var.upload_code
    COMBUSTION_ATLAS_UPLOADS_PER_USER_DAY    = tostring(var.uploads_per_user_day)
    },
    # Backup answer model on Azure OpenAI, used only when OpenAI is down after retries.
    { for k, v in {
      COMBUSTION_ATLAS_FALLBACK_MODEL            = var.azure_openai_answer_model
      COMBUSTION_ATLAS_FALLBACK_BASE_URL         = var.azure_openai_enabled ? "${azurerm_cognitive_account.openai[0].endpoint}openai/v1/" : ""
      COMBUSTION_ATLAS_FALLBACK_API_KEY          = var.azure_openai_enabled ? azurerm_cognitive_account.openai[0].primary_access_key : ""
      COMBUSTION_ATLAS_FALLBACK_REASONING_EFFORT = "low"
    } : k => v if var.azure_openai_enabled }
  )

  auth_settings_v2 {
    auth_enabled = true
    # Public access: sign-in is optional; the app still checks admin identity itself.
    require_authentication = !var.public_access
    require_https          = true
    unauthenticated_action = var.public_access ? "AllowAnonymous" : "RedirectToLoginPage"
    default_provider       = local.use_github ? "github" : "azureactivedirectory"
    excluded_paths         = ["/api/health"]

    # Microsoft (Entra ID) sign-in, restricted by "assignment required" in the directory.
    dynamic "active_directory_v2" {
      for_each = local.use_github ? [] : [1]
      content {
        client_id                  = azuread_application.signin.client_id
        tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azuread_client_config.current.tenant_id}/v2.0"
        client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"
        # Request only what the app needs to identify the user. "profile" and
        # "offline_access" need an admin's approval in some directories (e.g. UChicago).
        login_parameters = {
          scope = "openid email"
        }
      }
    }

    # GitHub sign-in admits any GitHub account: the app enforces allowed_users.
    dynamic "github_v2" {
      for_each = local.use_github ? [1] : []
      content {
        client_id                  = var.github_oauth_client_id
        client_secret_setting_name = "GITHUB_PROVIDER_AUTHENTICATION_SECRET"
      }
    }

    login {
      token_store_enabled = true
    }
  }
}
