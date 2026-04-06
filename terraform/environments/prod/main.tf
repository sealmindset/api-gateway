###############################################################################
# Production Environment
# High availability, larger instances, strict security, geo-redundant backups.
###############################################################################

terraform {
  required_version = ">= 1.5"

  backend "azurerm" {
    resource_group_name  = "terraform-state-rg"
    storage_account_name = "tfstateapigateway"
    container_name       = "tfstate"
    key                  = "api-gateway-prod.tfstate"
  }
}

module "api_gateway" {
  source = "../../"

  environment         = "prod"
  location            = "eastus2"
  resource_group_name = "apigw-prod-rg"

  tags = {
    team        = "platform"
    cost_center = "engineering"
    compliance  = "soc2"
    data_class  = "confidential"
  }

  # ---------------------------------------------------------------------------
  # Networking - WAF_v2 with full protection
  # ---------------------------------------------------------------------------
  vnet_address_space         = ["10.30.0.0/16"]
  aks_subnet_prefix          = "10.30.0.0/20"
  database_subnet_prefix     = "10.30.16.0/24"
  monitoring_subnet_prefix   = "10.30.17.0/24"
  gateway_subnet_prefix      = "10.30.18.0/24"
  enable_application_gateway = true
  app_gateway_sku            = "WAF_v2"

  # ---------------------------------------------------------------------------
  # Database - general purpose, zone-redundant HA, geo-redundant backups
  # ---------------------------------------------------------------------------
  postgresql_sku            = "GP_Standard_D4s_v3"
  postgresql_storage_mb     = 131072
  postgresql_version        = "15"
  db_administrator_login    = "pgadmin"
  db_administrator_password = var.db_administrator_password
  db_backup_retention_days  = 35
  db_geo_redundant_backup   = true
  db_high_availability_enabled = true

  # ---------------------------------------------------------------------------
  # AKS / Kong - production-grade cluster with Premium Redis
  # ---------------------------------------------------------------------------
  kubernetes_version         = "1.28"
  aks_default_node_pool_size = 5
  aks_default_node_pool_min  = 3
  aks_default_node_pool_max  = 20
  aks_vm_size                = "Standard_D8s_v3"
  redis_sku                  = "Premium"
  redis_capacity             = 1
  redis_family               = "P"

  # ---------------------------------------------------------------------------
  # Monitoring - long retention, standard Grafana with zone redundancy
  # ---------------------------------------------------------------------------
  log_retention_days      = 90
  grafana_sku             = "Standard"
  grafana_admin_group_ids = var.grafana_admin_group_ids

  # ---------------------------------------------------------------------------
  # Autoscaling - high headroom for traffic spikes
  # ---------------------------------------------------------------------------
  kong_proxy_min_replicas        = 3
  kong_proxy_max_replicas        = 50
  kong_proxy_target_rps          = "1000"
  kong_proxy_target_latency_ms   = "50"
  admin_panel_min_replicas       = 2
  admin_panel_max_replicas       = 10
  admin_panel_target_cpu_percent = 60
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

output "prometheus_endpoint" {
  value = module.api_gateway.prometheus_endpoint
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

output "key_vault_uri" {
  value = module.api_gateway.key_vault_uri
}

output "redis_hostname" {
  value = module.api_gateway.redis_hostname
}
