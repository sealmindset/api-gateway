###############################################################################
# Database Module - Outputs
###############################################################################

output "postgresql_server_id" {
  description = "ID of the PostgreSQL Flexible Server"
  value       = azurerm_postgresql_flexible_server.main.id
}

output "postgresql_fqdn" {
  description = "Fully qualified domain name of the PostgreSQL server"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "administrator_login" {
  description = "Administrator login username"
  value       = azurerm_postgresql_flexible_server.main.administrator_login
}

output "kong_database_name" {
  description = "Name of the Kong database"
  value       = azurerm_postgresql_flexible_server_database.kong.name
}

output "admin_panel_database_name" {
  description = "Name of the admin panel database"
  value       = azurerm_postgresql_flexible_server_database.admin_panel.name
}

output "kong_connection_string" {
  description = "Connection string for the Kong database"
  value       = "postgresql://${azurerm_postgresql_flexible_server.main.administrator_login}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.kong.name}?sslmode=require"
  sensitive   = true
}

output "admin_panel_connection_string" {
  description = "Connection string for the admin panel database"
  value       = "postgresql://${azurerm_postgresql_flexible_server.main.administrator_login}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.admin_panel.name}?sslmode=require"
  sensitive   = true
}
