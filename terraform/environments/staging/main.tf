###############################################################################
# Staging Environment
# Matches production topology at smaller scale for pre-release validation.
###############################################################################

terraform {
  required_version = ">= 1.5"

  backend "azurerm" {
    resource_group_name  = "terraform-state-rg"
    storage_account_name = "tfstateapigateway"
    container_name       = "tfstate"
    key                  = "api-gateway-staging.tfstate"
  }
}

module "api_gateway" {
  source = "../../"

  environment         = "staging"
  location            = "eastus2"
  resource_group_name = "apigw-staging-rg"

  tags = {
    team        = "platform"
    cost_center = "engineering"
  }

  # ---------------------------------------------------------------------------
  # Networking - same topology as prod, WAF enabled
  # ---------------------------------------------------------------------------
  vnet_address_space         = ["10.20.0.0/16"]
  aks_subnet_prefix          = "10.20.0.0/20"
  database_subnet_prefix     = "10.20.16.0/24"
  monitoring_subnet_prefix   = "10.20.17.0/24"
  gateway_subnet_prefix      = "10.20.18.0/24"
  enable_application_gateway = true
  app_gateway_sku            = "WAF_v2"

  # ---------------------------------------------------------------------------
  # Database - general purpose, no HA, geo-backup off
  # ---------------------------------------------------------------------------
  postgresql_sku            = "GP_Standard_D2s_v3"
  postgresql_storage_mb     = 65536
  postgresql_version        = "15"
  db_administrator_login    = "pgadmin"
  db_administrator_password = var.db_administrator_password
  db_backup_retention_days  = 14
  db_geo_redundant_backup   = false
  db_high_availability_enabled = false

  # ---------------------------------------------------------------------------
  # AKS / Kong - moderate cluster matching prod structure
  # ---------------------------------------------------------------------------
  kubernetes_version         = "1.28"
  aks_default_node_pool_size = 3
  aks_default_node_pool_min  = 2
  aks_default_node_pool_max  = 6
  aks_vm_size                = "Standard_D4s_v3"
  redis_sku                  = "Standard"
  redis_capacity             = 1
  redis_family               = "C"

  # ---------------------------------------------------------------------------
  # Monitoring - moderate retention, standard Grafana
  # ---------------------------------------------------------------------------
  log_retention_days      = 30
  grafana_sku             = "Standard"
  grafana_admin_group_ids = var.grafana_admin_group_ids

  # ---------------------------------------------------------------------------
  # Autoscaling - mirrors prod ratios at smaller scale
  # ---------------------------------------------------------------------------
  kong_proxy_min_replicas        = 2
  kong_proxy_max_replicas        = 10
  kong_proxy_target_rps          = "1000"
  kong_proxy_target_latency_ms   = "100"
  admin_panel_min_replicas       = 1
  admin_panel_max_replicas       = 3
  admin_panel_target_cpu_percent = 70
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "db_administrator_password" {
  description = "PostgreSQL administrator password"
  type        = string
  sensitive   = true
}

variable "grafana_admin_group_ids" {
  description = "Azure AD group IDs for Grafana admin access"
  type        = list(string)
  default     = []
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "gateway_url" {
  value = module.api_gateway.gateway_url
}

output "admin_panel_url" {
  value = module.api_gateway.admin_panel_url
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

output "postgresql_fqdn" {
  value = module.api_gateway.postgresql_fqdn
}
