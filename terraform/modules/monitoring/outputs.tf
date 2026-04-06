###############################################################################
# Monitoring Module - Outputs
###############################################################################

output "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace"
  value       = azurerm_log_analytics_workspace.main.id
}

output "log_analytics_workspace_name" {
  description = "Name of the Log Analytics workspace"
  value       = azurerm_log_analytics_workspace.main.name
}

output "log_analytics_primary_key" {
  description = "Primary shared key for the Log Analytics workspace"
  value       = azurerm_log_analytics_workspace.main.primary_shared_key
  sensitive   = true
}

output "monitor_workspace_id" {
  description = "ID of the Azure Monitor workspace"
  value       = azurerm_monitor_workspace.main.id
}

output "prometheus_endpoint" {
  description = "Prometheus query endpoint"
  value       = azurerm_monitor_workspace.main.query_endpoint
}

output "grafana_endpoint" {
  description = "Grafana dashboard endpoint URL"
  value       = azurerm_dashboard_grafana.main.endpoint
}

output "grafana_id" {
  description = "ID of the Managed Grafana instance"
  value       = azurerm_dashboard_grafana.main.id
}

output "action_group_id" {
  description = "ID of the critical alerts action group"
  value       = azurerm_monitor_action_group.critical.id
}
