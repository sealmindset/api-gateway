###############################################################################
# Monitoring Module
# Azure Monitor workspace, Log Analytics, Managed Grafana, Managed
# Prometheus, and diagnostic settings for the AKS cluster.
###############################################################################

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "azurerm_client_config" "current" {}

# -----------------------------------------------------------------------------
# Log Analytics Workspace
# -----------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.name_prefix}-law"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  tags                = var.tags

  daily_quota_gb = var.environment == "dev" ? 1 : -1
}

resource "azurerm_log_analytics_solution" "container_insights" {
  solution_name         = "ContainerInsights"
  location              = var.location
  resource_group_name   = var.resource_group_name
  workspace_resource_id = azurerm_log_analytics_workspace.main.id
  workspace_name        = azurerm_log_analytics_workspace.main.name
  tags                  = var.tags

  plan {
    publisher = "Microsoft"
    product   = "OMSGallery/ContainerInsights"
  }
}

# -----------------------------------------------------------------------------
# Azure Monitor Workspace (for Prometheus metrics)
# -----------------------------------------------------------------------------

resource "azurerm_monitor_workspace" "main" {
  name                = "${var.name_prefix}-amw"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

# -----------------------------------------------------------------------------
# Azure Managed Prometheus - Data Collection
# -----------------------------------------------------------------------------

resource "azurerm_monitor_data_collection_endpoint" "prometheus" {
  name                = "${var.name_prefix}-prometheus-dce"
  location            = var.location
  resource_group_name = var.resource_group_name
  kind                = "Linux"
  tags                = var.tags
}

resource "azurerm_monitor_data_collection_rule" "prometheus" {
  name                        = "${var.name_prefix}-prometheus-dcr"
  location                    = var.location
  resource_group_name         = var.resource_group_name
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.prometheus.id
  kind                        = "Linux"
  tags                        = var.tags

  destinations {
    monitor_account {
      monitor_account_id = azurerm_monitor_workspace.main.id
      name               = "MonitoringAccount"
    }
  }

  data_flow {
    streams      = ["Microsoft-PrometheusMetrics"]
    destinations = ["MonitoringAccount"]
  }

  data_sources {
    prometheus_forwarder {
      streams = ["Microsoft-PrometheusMetrics"]
      name    = "PrometheusDataSource"
    }
  }
}

resource "azurerm_monitor_data_collection_rule_association" "prometheus" {
  name                    = "${var.name_prefix}-prometheus-dcra"
  target_resource_id      = var.aks_cluster_id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.prometheus.id
}

# -----------------------------------------------------------------------------
# Azure Managed Grafana
# -----------------------------------------------------------------------------

resource "azurerm_dashboard_grafana" "main" {
  name                              = "${var.name_prefix}-grafana"
  location                          = var.location
  resource_group_name               = var.resource_group_name
  sku                               = var.grafana_sku
  zone_redundancy_enabled           = var.environment == "prod" ? true : false
  api_key_enabled                   = true
  deterministic_outbound_ip_enabled = true
  public_network_access_enabled     = true
  tags                              = var.tags

  azure_monitor_workspace_integrations {
    resource_id = azurerm_monitor_workspace.main.id
  }

  identity {
    type = "SystemAssigned"
  }
}

# Grant Grafana read access to the Monitor workspace
resource "azurerm_role_assignment" "grafana_monitor_reader" {
  scope                = azurerm_monitor_workspace.main.id
  role_definition_name = "Monitoring Reader"
  principal_id         = azurerm_dashboard_grafana.main.identity[0].principal_id
}

# Grant Grafana read access to Log Analytics
resource "azurerm_role_assignment" "grafana_law_reader" {
  scope                = azurerm_log_analytics_workspace.main.id
  role_definition_name = "Log Analytics Reader"
  principal_id         = azurerm_dashboard_grafana.main.identity[0].principal_id
}

# Grant admin groups Grafana Admin role
resource "azurerm_role_assignment" "grafana_admin" {
  for_each = toset(var.grafana_admin_group_ids)

  scope                = azurerm_dashboard_grafana.main.id
  role_definition_name = "Grafana Admin"
  principal_id         = each.value
}

# -----------------------------------------------------------------------------
# Diagnostic Settings for AKS
# -----------------------------------------------------------------------------

resource "azurerm_monitor_diagnostic_setting" "aks" {
  name                       = "${var.name_prefix}-aks-diag"
  target_resource_id         = var.aks_cluster_id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "kube-apiserver"
  }

  enabled_log {
    category = "kube-audit-admin"
  }

  enabled_log {
    category = "kube-controller-manager"
  }

  enabled_log {
    category = "kube-scheduler"
  }

  enabled_log {
    category = "guard"
  }

  metric {
    category = "AllMetrics"
    enabled  = true
  }
}

# -----------------------------------------------------------------------------
# Action Group for Alerts
# -----------------------------------------------------------------------------

resource "azurerm_monitor_action_group" "critical" {
  name                = "${var.name_prefix}-critical-ag"
  resource_group_name = var.resource_group_name
  short_name          = "CritAlert"
  tags                = var.tags
}

# -----------------------------------------------------------------------------
# Metric Alerts
# -----------------------------------------------------------------------------

resource "azurerm_monitor_metric_alert" "aks_node_cpu" {
  name                = "${var.name_prefix}-aks-node-cpu-alert"
  resource_group_name = var.resource_group_name
  scopes              = [var.aks_cluster_id]
  description         = "Alert when AKS node CPU exceeds 85%"
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"
  tags                = var.tags

  criteria {
    metric_namespace = "Insights.Container/nodes"
    metric_name      = "cpuUsagePercentage"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 85
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

resource "azurerm_monitor_metric_alert" "aks_node_memory" {
  name                = "${var.name_prefix}-aks-node-memory-alert"
  resource_group_name = var.resource_group_name
  scopes              = [var.aks_cluster_id]
  description         = "Alert when AKS node memory exceeds 85%"
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"
  tags                = var.tags

  criteria {
    metric_namespace = "Insights.Container/nodes"
    metric_name      = "memoryWorkingSetPercentage"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 85
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}
