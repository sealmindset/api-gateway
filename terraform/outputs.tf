###############################################################################
# API Gateway - Root Outputs
###############################################################################

# -----------------------------------------------------------------------------
# Gateway Endpoints
# -----------------------------------------------------------------------------

output "gateway_public_ip" {
  description = "Public IP address of the API Gateway"
  value       = module.networking.gateway_public_ip
}

output "gateway_url" {
  description = "URL for the API Gateway proxy endpoint"
  value       = "https://${module.networking.gateway_fqdn}"
}

output "admin_panel_url" {
  description = "URL for the Kong admin panel"
  value       = "https://${module.networking.gateway_fqdn}/admin"
}

# -----------------------------------------------------------------------------
# Monitoring
# -----------------------------------------------------------------------------

output "grafana_url" {
  description = "URL for the Azure Managed Grafana dashboard"
  value       = module.monitoring.grafana_endpoint
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID for querying logs"
  value       = module.monitoring.log_analytics_workspace_id
}

output "prometheus_endpoint" {
  description = "Prometheus query endpoint"
  value       = module.monitoring.prometheus_endpoint
}

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

output "postgresql_fqdn" {
  description = "Fully qualified domain name of the PostgreSQL server"
  value       = module.database.postgresql_fqdn
}

output "kong_db_connection_string" {
  description = "Connection string for the Kong database"
  value       = module.database.kong_connection_string
  sensitive   = true
}

output "admin_panel_db_connection_string" {
  description = "Connection string for the admin panel database"
  value       = module.database.admin_panel_connection_string
  sensitive   = true
}

# -----------------------------------------------------------------------------
# AKS / Container Infrastructure
# -----------------------------------------------------------------------------

output "aks_cluster_name" {
  description = "Name of the AKS cluster"
  value       = module.kong.aks_cluster_name
}

output "acr_login_server" {
  description = "Login server URL for Azure Container Registry"
  value       = module.kong.acr_login_server
}

output "key_vault_uri" {
  description = "URI of the Key Vault storing secrets"
  value       = module.kong.key_vault_uri
}

output "redis_hostname" {
  description = "Hostname of the Azure Redis Cache instance"
  value       = module.kong.redis_hostname
}
