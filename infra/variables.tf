# --- Azure ---------------------------------------------------------------

variable "subscription_id" {
  description = "Azure subscription ID to deploy into."
  type        = string
}

variable "location" {
  description = "Azure region, e.g. westeurope or eastus."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group to create."
  type        = string
  default     = "combustion-atlas"
}

variable "app_name" {
  description = "Web app name (globally unique). The host becomes <app_name>.azurewebsites.net."
  type        = string
}

variable "app_service_sku" {
  description = "App Service plan SKU."
  type        = string
  default     = "B1"
}

# --- App settings --------------------------------------------------------

variable "openai_api_key" {
  description = "OpenAI API key. Pass via TF_VAR_openai_api_key; never commit it."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.openai_api_key) > 0
    error_message = "openai_api_key must be set (export TF_VAR_openai_api_key)."
  }
}

variable "embedding_model" {
  description = "Embedding model. Must match the model used to build the uploaded index."
  type        = string
  default     = "text-embedding-3-small"
}

variable "answer_model" {
  description = "Answer model."
  type        = string
  default     = "gpt-6-luna"
}

variable "admin_emails" {
  description = "Emails of app admins (written to COMBUSTION_ATLAS_ADMINS, comma-separated)."
  type        = list(string)
  default     = []
}

# --- Sign-in -------------------------------------------------------------

variable "allowed_user_principal_names" {
  description = "Existing users in this tenant allowed to sign in (user principal names)."
  type        = list(string)
  default     = []
}

variable "guest_emails" {
  description = "External people to invite as guests and allow to sign in."
  type        = list(string)
  default     = []
}

# --- GitHub --------------------------------------------------------------

variable "github_owner" {
  description = "GitHub user or organization that owns the repository."
  type        = string
  default     = "sophie-lara"
}

variable "github_repository" {
  description = "GitHub repository name."
  type        = string
  default     = "free-fall-flame-lab"
}

variable "github_branch" {
  description = "Branch allowed to deploy (federated credential subject)."
  type        = string
  default     = "main"
}

variable "deploy_approvers" {
  description = "Comma-separated GitHub usernames allowed to run the deploy workflow."
  type        = string
  default     = "sophie-lara"
}

variable "auth_provider" {
  description = "Sign-in provider for the web app: \"microsoft\" (Entra ID) or \"github\"."
  type        = string
  default     = "microsoft"

  validation {
    condition     = contains(["microsoft", "github"], var.auth_provider)
    error_message = "auth_provider must be \"microsoft\" or \"github\"."
  }
}

variable "github_oauth_client_id" {
  description = "Client ID of the GitHub OAuth App used for sign-in (auth_provider = \"github\")."
  type        = string
  default     = ""
}

variable "github_oauth_client_secret" {
  description = "GitHub OAuth App client secret. Pass via TF_VAR_github_oauth_client_secret."
  type        = string
  default     = ""
  sensitive   = true
}

variable "allowed_users" {
  description = "Sign-in names (GitHub usernames or emails) allowed to use the app; admins are always allowed. Required with GitHub sign-in, which admits any GitHub account."
  type        = list(string)
  default     = []
}
