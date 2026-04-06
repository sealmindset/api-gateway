###############################################################################
# Kong Module - Variables
###############################################################################

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
}

variable "aks_subnet_id" {
  description = "ID of the AKS subnet"
  type        = string
}

variable "vnet_id" {
  description = "ID of the virtual network"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version for AKS"
  type        = string
}

variable "aks_default_node_pool_size" {
  description = "Initial node count for the default node pool"
  type        = number
}

variable "aks_default_node_pool_min" {
  description = "Minimum node count for autoscaler"
  type        = number
}

variable "aks_default_node_pool_max" {
  description = "Maximum node count for autoscaler"
  type        = number
}

variable "aks_vm_size" {
  description = "VM size for AKS node pools"
  type        = string
}

variable "redis_sku" {
  description = "SKU name for Azure Redis Cache"
  type        = string
}

variable "redis_capacity" {
  description = "Size of the Redis cache"
  type        = number
}

variable "redis_family" {
  description = "Redis cache family"
  type        = string
}

variable "kong_db_host" {
  description = "PostgreSQL server FQDN for Kong"
  type        = string
}

variable "kong_db_name" {
  description = "Database name for Kong"
  type        = string
}

variable "kong_db_user" {
  description = "Database user for Kong"
  type        = string
}

variable "kong_db_password" {
  description = "Database password for Kong"
  type        = string
  sensitive   = true
}

variable "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace for AKS monitoring"
  type        = string
}
