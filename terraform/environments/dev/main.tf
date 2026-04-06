###############################################################################
# Dev Environment
# Smaller instance sizes, relaxed security settings, lower costs.
###############################################################################

terraform {
  required_version = ">= 1.5"

  backend "azurerm" {
    resource_group_name  = "terraform-state-rg"
    storage_account_name = "tfstateapigateway"
    container_name       = "tfstate"
    key                  = "api-gateway-dev.tfstate"
  }
}

module "api_gateway" {
  source = "../../"

  environment         = "dev"
  location            = "eastus2"
  resource_group_name = "apigw-dev-rg"

  tags = {
    team        = "platform"
    cost_center = "engineering"
  }

  # ---------------------------------------------------------------------------
  # Networking - standard address space
  # ---------------------------------------------------------------------------
  vnet_address_space         = ["10.10.0.0/16"]
  aks_subnet_prefix          = "10.10.0.0/20"
  database_subnet_prefix     = "10.10.16.0/24"
  monitoring_subnet_prefix   = "10.10.17.0/24"
  gateway_subnet_prefix      = "10.10.18.0/24"
  enable_application_gateway = false  # Use basic LB in dev to save cost
  app_gateway_sku            = "Standard_v2"

  # ---------------------------------------------------------------------------
  # Database - smallest viable tier, no HA
  # ---------------------------------------------------------------------------
  postgresql_sku            = "B_Standard_B1ms"
  postgresql_storage_mb     = 32768
  postgresql_version        = "15"
  db_administrator_login    = "pgadmin"
  db_administrator_password = var.db_administrator_password
  db_backup_retention_days  = 7
  db_geo_redundant_backup   = false
  db_high_availability_enabled = false

  # ---------------------------------------------------------------------------
  # AKS / Kong - minimal cluster
  # ---------------------------------------------------------------------------
  kubernetes_version         = "1.28"
  aks_default_node_pool_size = 2
  aks_default_node_pool_min  = 1
  aks_default_node_pool_max  = 4
  aks_vm_size                = "Standard_D2s_v3"
  redis_sku                  = "Basic"
  redis_capacity             = 0
  redis_family               = "C"

  # ---------------------------------------------------------------------------
  # Monitoring - short retention, essential Grafana
  # ---------------------------------------------------------------------------
  log_retention_days      = 14
  grafana_sku             = "Essential"
  grafana_admin_group_ids = []

  # ---------------------------------------------------------------------------
  # Autoscaling - conservative limits
  # ---------------------------------------------------------------------------
  kong_proxy_min_replicas        = 1
  kong_proxy_max_replicas        = 4
  kong_proxy_target_rps          = "500"
  kong_proxy_target_latency_ms   = "200"
  admin_panel_min_replicas       = 1
  admin_panel_max_replicas       = 2
  admin_panel_target_cpu_percent = 80
}

# ---------------------------------------------------------------------------
# Variables (secrets passed via CI/CD or tfvars)
# ---------------------------------------------------------------------------

variable "db_administrator_password" {
  description = "PostgreSQL administrator password"
  type        = string
  sensitive   = true
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "gateway_url" {
  value = module.api_gateway.gateway_url
}

output "grafana_url" {
  value = module.api_gateway.grafana_url
}

output "aks_cluster_name" {
  value = module.api_gateway.aks_cluster_name
}

output "acr_login_server" {
  value = module.api_gateway.acr_login_server
}
