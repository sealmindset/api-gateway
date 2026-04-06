###############################################################################
# API Gateway - Root Module
# Deploys Kong API Gateway on Azure with AKS, PostgreSQL, monitoring, and
# autoscaling infrastructure.
###############################################################################

terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.85"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }

  backend "azurerm" {
    resource_group_name  = "terraform-state-rg"
    storage_account_name = "tfstateapigateway"
    container_name       = "tfstate"
    key                  = "api-gateway.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}

###############################################################################
# Resource Group
###############################################################################

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}

###############################################################################
# Locals
###############################################################################

locals {
  common_tags = merge(var.tags, {
    environment = var.environment
    managed_by  = "terraform"
    project     = "api-gateway"
  })

  name_prefix = "apigw-${var.environment}"
}

###############################################################################
# Networking Module
###############################################################################

module "networking" {
  source = "./modules/networking"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  environment         = var.environment
  name_prefix         = local.name_prefix
  tags                = local.common_tags

  vnet_address_space        = var.vnet_address_space
  aks_subnet_prefix         = var.aks_subnet_prefix
  database_subnet_prefix    = var.database_subnet_prefix
  monitoring_subnet_prefix  = var.monitoring_subnet_prefix
  gateway_subnet_prefix     = var.gateway_subnet_prefix
  enable_application_gateway = var.enable_application_gateway
  app_gateway_sku           = var.app_gateway_sku
}

###############################################################################
# Database Module
###############################################################################

module "database" {
  source = "./modules/database"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  environment         = var.environment
  name_prefix         = local.name_prefix
  tags                = local.common_tags

  database_subnet_id       = module.networking.database_subnet_id
  private_dns_zone_id      = module.networking.postgresql_private_dns_zone_id
  vnet_id                  = module.networking.vnet_id
  postgresql_sku           = var.postgresql_sku
  postgresql_storage_mb    = var.postgresql_storage_mb
  postgresql_version        = var.postgresql_version
  administrator_login      = var.db_administrator_login
  administrator_password   = var.db_administrator_password
  backup_retention_days    = var.db_backup_retention_days
  geo_redundant_backup     = var.db_geo_redundant_backup
  high_availability_enabled = var.db_high_availability_enabled
}

###############################################################################
# Kong Module (AKS + ACR + KeyVault + Redis)
###############################################################################

module "kong" {
  source = "./modules/kong"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  environment         = var.environment
  name_prefix         = local.name_prefix
  tags                = local.common_tags

  aks_subnet_id              = module.networking.aks_subnet_id
  vnet_id                    = module.networking.vnet_id
  kubernetes_version         = var.kubernetes_version
  aks_default_node_pool_size = var.aks_default_node_pool_size
  aks_default_node_pool_min  = var.aks_default_node_pool_min
  aks_default_node_pool_max  = var.aks_default_node_pool_max
  aks_vm_size                = var.aks_vm_size
  redis_sku                  = var.redis_sku
  redis_capacity             = var.redis_capacity
  redis_family               = var.redis_family

  kong_db_host     = module.database.postgresql_fqdn
  kong_db_name     = module.database.kong_database_name
  kong_db_user     = module.database.administrator_login
  kong_db_password = var.db_administrator_password

  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
}

###############################################################################
# Monitoring Module
###############################################################################

module "monitoring" {
  source = "./modules/monitoring"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  environment         = var.environment
  name_prefix         = local.name_prefix
  tags                = local.common_tags

  monitoring_subnet_id    = module.networking.monitoring_subnet_id
  aks_cluster_id          = module.kong.aks_cluster_id
  log_retention_days      = var.log_retention_days
  grafana_sku             = var.grafana_sku
  grafana_admin_group_ids = var.grafana_admin_group_ids
}

###############################################################################
# Autoscaling Module
###############################################################################

module "autoscaling" {
  source = "./modules/autoscaling"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  environment         = var.environment
  name_prefix         = local.name_prefix
  tags                = local.common_tags

  aks_cluster_id   = module.kong.aks_cluster_id
  aks_cluster_name = module.kong.aks_cluster_name

  kong_proxy_min_replicas        = var.kong_proxy_min_replicas
  kong_proxy_max_replicas        = var.kong_proxy_max_replicas
  kong_proxy_target_rps          = var.kong_proxy_target_rps
  kong_proxy_target_latency_ms   = var.kong_proxy_target_latency_ms
  admin_panel_min_replicas       = var.admin_panel_min_replicas
  admin_panel_max_replicas       = var.admin_panel_max_replicas
  admin_panel_target_cpu_percent = var.admin_panel_target_cpu_percent

  prometheus_server_url = module.monitoring.prometheus_endpoint

  node_pool_min_count = var.aks_default_node_pool_min
  node_pool_max_count = var.aks_default_node_pool_max

  depends_on = [module.kong, module.monitoring]
}
