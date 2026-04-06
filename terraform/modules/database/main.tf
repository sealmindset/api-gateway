###############################################################################
# Database Module
# Azure Database for PostgreSQL Flexible Server with private networking,
# Kong and admin-panel databases, and backup configuration.
###############################################################################

# -----------------------------------------------------------------------------
# PostgreSQL Flexible Server
# -----------------------------------------------------------------------------

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "${var.name_prefix}-pgflex"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  version                       = var.postgresql_version
  administrator_login           = var.administrator_login
  administrator_password        = var.administrator_password
  storage_mb                    = var.postgresql_storage_mb
  sku_name                      = var.postgresql_sku
  delegated_subnet_id           = var.database_subnet_id
  private_dns_zone_id           = var.private_dns_zone_id
  public_network_access_enabled = false
  zone                          = "1"
  tags                          = var.tags

  backup_retention_days        = var.backup_retention_days
  geo_redundant_backup_enabled = var.geo_redundant_backup

  dynamic "high_availability" {
    for_each = var.high_availability_enabled ? [1] : []
    content {
      mode                      = "ZoneRedundant"
      standby_availability_zone = "2"
    }
  }

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

# -----------------------------------------------------------------------------
# Server Configuration
# -----------------------------------------------------------------------------

resource "azurerm_postgresql_flexible_server_configuration" "log_checkpoints" {
  name      = "log_checkpoints"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_connections" {
  name      = "log_connections"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_disconnections" {
  name      = "log_disconnections"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "connection_throttling" {
  name      = "connection_throttle.enable"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "pgaudit" {
  name      = "shared_preload_libraries"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "pgaudit"
}

# -----------------------------------------------------------------------------
# Databases
# -----------------------------------------------------------------------------

resource "azurerm_postgresql_flexible_server_database" "kong" {
  name      = "kong"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

resource "azurerm_postgresql_flexible_server_database" "admin_panel" {
  name      = "admin_panel"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# -----------------------------------------------------------------------------
# Firewall Rules (VNet access only - public access is already disabled)
# These serve as an additional layer if public access is ever enabled.
# -----------------------------------------------------------------------------

resource "azurerm_postgresql_flexible_server_firewall_rule" "deny_all_public" {
  name             = "deny-all-public"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
