# Microsoft sign-in (Easy Auth) app registration and the people allowed in.

resource "azuread_application" "signin" {
  display_name     = "${var.app_name}-signin"
  sign_in_audience = "AzureADMyOrg"
  owners           = [data.azuread_client_config.current.object_id]

  web {
    redirect_uris = ["https://${local.app_host}/.auth/login/aad/callback"]

    implicit_grant {
      id_token_issuance_enabled = true
    }
  }

  # Microsoft Graph: User.Read (delegated), used by Easy Auth sign-in.
  required_resource_access {
    resource_app_id = "00000003-0000-0000-c000-000000000000"

    resource_access {
      id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"
      type = "Scope"
    }
  }
}

# Expires after the azuread default (2 years); `terraform apply -replace` to rotate.
resource "azuread_application_password" "signin" {
  application_id = azuread_application.signin.id
  display_name   = "easy-auth"
}

resource "azuread_service_principal" "signin" {
  client_id                    = azuread_application.signin.client_id
  app_role_assignment_required = true # only assigned users can sign in
  owners                       = [data.azuread_client_config.current.object_id]
}

data "azuread_user" "allowed" {
  for_each            = toset(var.allowed_user_principal_names)
  user_principal_name = each.value
}

resource "azuread_invitation" "guest" {
  for_each           = toset(var.guest_emails)
  user_email_address = each.value
  redirect_url       = "https://${local.app_host}"

  message {
    body = "You have been invited to Combustion Atlas."
  }
}

resource "azuread_app_role_assignment" "member" {
  for_each = { for upn, user in data.azuread_user.allowed : upn => user.object_id }

  app_role_id         = local.default_app_role_id
  principal_object_id = each.value
  resource_object_id  = azuread_service_principal.signin.object_id
}

resource "azuread_app_role_assignment" "guest" {
  for_each = azuread_invitation.guest

  app_role_id         = local.default_app_role_id
  principal_object_id = each.value.user_id
  resource_object_id  = azuread_service_principal.signin.object_id
}
