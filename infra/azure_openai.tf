# Optional Azure OpenAI account (billed to the Azure subscription) serving the backup
# answer model: the app answers with it only when OpenAI is unavailable after retries.
# Off by default. Free-trial quota allows gpt-5-mini, gpt-4.1-mini
# and o4-mini (not gpt-6-luna); check: az cognitiveservices usage list -l <region>.

resource "azurerm_cognitive_account" "openai" {
  count                 = var.azure_openai_enabled ? 1 : 0
  name                  = "${var.app_name}-openai"
  custom_subdomain_name = "${var.app_name}-openai"
  location              = var.location
  resource_group_name   = azurerm_resource_group.main.name
  kind                  = "OpenAI"
  sku_name              = "S0"
}

resource "azurerm_cognitive_deployment" "answer" {
  count                = var.azure_openai_enabled ? 1 : 0
  name                 = var.azure_openai_answer_model
  cognitive_account_id = azurerm_cognitive_account.openai[0].id

  model {
    format  = "OpenAI"
    name    = var.azure_openai_answer_model
    version = var.azure_openai_answer_model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.azure_openai_capacity_k_tpm
  }
}
