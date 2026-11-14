output "app_url" {
  description = "Public URL of the app (Microsoft sign-in required)."
  value       = "https://${azurerm_linux_web_app.main.default_hostname}"
}

output "app_name" {
  description = "Web app name."
  value       = azurerm_linux_web_app.main.name
}

output "resource_group" {
  description = "Resource group name."
  value       = azurerm_resource_group.main.name
}

output "signin_client_id" {
  description = "Client ID of the Easy Auth sign-in app registration."
  value       = azuread_application.signin.client_id
}

output "next_steps" {
  description = "What to do after apply."
  value       = <<-EOT
    1. Upload the evidence data (dry run first):
         scripts/azure_upload_data.sh ${azurerm_linux_web_app.main.name} ${azurerm_resource_group.main.name}
         scripts/azure_upload_data.sh ${azurerm_linux_web_app.main.name} ${azurerm_resource_group.main.name} --upload
    2. Deploy code: GitHub Actions -> Deploy to Azure -> Run workflow on ${var.github_branch}, type "deploy".
    3. Open https://${azurerm_linux_web_app.main.default_hostname} in a private window and sign in.
  EOT
}
