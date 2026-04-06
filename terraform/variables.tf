###############################################################################
# API Gateway - Root Variables
###############################################################################

# -----------------------------------------------------------------------------
# General
# -----------------------------------------------------------------------------

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus2"
}

variable "resource_group_name" {
  description = "Name of the Azure resource group"
  type        = string
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# Networking
# -----------------------------------------------------------------------------

variable "vnet_address_space" {
  description = "Address space for the virtual network"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "aks_subnet_prefix" {
  description = "CIDR prefix for the AKS subnet"
  type        = string
  default     = "10.0.0.0/20"
}

variable "database_subnet_prefix" {
  description = "CIDR prefix for the database subnet"
  type        = string
  default     = "10.0.16.0/24"
}

variable "monitoring_subnet_prefix" {
  description = "CIDR prefix for the monitoring subnet"
  type        = string
  default     = "10.0.17.0/24"
}

variable "gateway_subnet_prefix" {
  description = "CIDR prefix for the application gateway subnet"
  type        = string
  default     = "10.0.18.0/24"
}

variable "enable_application_gateway" {
  description = "Whether to deploy Azure Application Gateway for ingress"
  type        = bool
  default     = true
}

variable "app_gateway_sku" {
  description = "SKU tier for the Application Gateway (Standard_v2 or WAF_v2)"
  type        = string
  default     = "WAF_v2"
}

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

variable "postgresql_sku" {
  description = "SKU name for PostgreSQL Flexible Server (e.g. GP_Standard_D2s_v3)"
  type        = string
  default     = "GP_Standard_D2s_v3"
}

variable "postgresql_storage_mb" {
  description = "Storage size in MB for PostgreSQL"
  type        = number
  default     = 32768
}

variable "postgresql_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15"
}

variable "db_administrator_login" {
  description = "Administrator login for PostgreSQL"
  type        = string
  default     = "pgadmin"
}

variable "db_administrator_password" {
  description = "Administrator password for PostgreSQL"
  type        = string
  sensitive   = true
}

variable "db_backup_retention_days" {
  description = "Number of days to retain PostgreSQL backups"
  type        = number
  default     = 7
}

variable "db_geo_redundant_backup" {
  description = "Enable geo-redundant backups for PostgreSQL"
  type        = bool
  default     = false
}

variable "db_high_availability_enabled" {
  description = "Enable zone-redundant high availability for PostgreSQL"
  type        = bool
  default     = false
}

# -----------------------------------------------------------------------------
# AKS / Kong
# -----------------------------------------------------------------------------

variable "kubernetes_version" {
  description = "Kubernetes version for AKS cluster"
  type        = string
  default     = "1.28"
}

variable "aks_default_node_pool_size" {
  description = "Initial node count for the default AKS node pool"
  type        = number
  default     = 3
}

variable "aks_default_node_pool_min" {
  description = "Minimum node count for AKS autoscaler"
  type        = number
  default     = 2
}

variable "aks_default_node_pool_max" {
  description = "Maximum node count for AKS autoscaler"
  type        = number
  default     = 10
}

variable "aks_vm_size" {
  description = "VM size for AKS default node pool"
  type        = string
  default     = "Standard_D4s_v3"
}

variable "redis_sku" {
  description = "SKU name for Azure Redis Cache (Basic, Standard, Premium)"
  type        = string
  default     = "Standard"
}

variable "redis_capacity" {
  description = "Size of the Redis cache (0-6)"
  type        = number
  default     = 1
}

variable "redis_family" {
  description = "Redis cache family (C for Basic/Standard, P for Premium)"
  type        = string
  default     = "C"
}

# -----------------------------------------------------------------------------
# Monitoring
# -----------------------------------------------------------------------------

variable "log_retention_days" {
  description = "Number of days to retain logs in Log Analytics"
  type        = number
  default     = 30
}

variable "grafana_sku" {
  description = "SKU for Azure Managed Grafana (Standard or Essential)"
  type        = string
  default     = "Standard"
}

variable "grafana_admin_group_ids" {
  description = "List of Azure AD group object IDs that should have Grafana admin access"
  type        = list(string)
  default     = []
}

# -----------------------------------------------------------------------------
# Autoscaling
# -----------------------------------------------------------------------------

variable "kong_proxy_min_replicas" {
  description = "Minimum replica count for Kong proxy pods"
  type        = number
  default     = 2
}

variable "kong_proxy_max_replicas" {
  description = "Maximum replica count for Kong proxy pods"
  type        = number
  default     = 20
}

variable "kong_proxy_target_rps" {
  description = "Target requests per second per pod for Kong proxy autoscaling"
  type        = string
  default     = "1000"
}

variable "kong_proxy_target_latency_ms" {
  description = "Target p95 latency in milliseconds for Kong proxy autoscaling"
  type        = string
  default     = "100"
}

variable "admin_panel_min_replicas" {
  description = "Minimum replica count for admin panel pods"
  type        = number
  default     = 1
}

variable "admin_panel_max_replicas" {
  description = "Maximum replica count for admin panel pods"
  type        = number
  default     = 5
}

variable "admin_panel_target_cpu_percent" {
  description = "Target CPU utilisation percentage for admin panel autoscaling"
  type        = number
  default     = 70
}
