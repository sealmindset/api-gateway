###############################################################################
# Monitoring Module - Variables
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

variable "monitoring_subnet_id" {
  description = "ID of the monitoring subnet"
  type        = string
}

variable "aks_cluster_id" {
  description = "ID of the AKS cluster for diagnostic settings"
  type        = string
}

variable "log_retention_days" {
  description = "Number of days to retain logs"
  type        = number
  default     = 30
}

variable "grafana_sku" {
  description = "SKU for Azure Managed Grafana"
  type        = string
  default     = "Standard"
}

variable "grafana_admin_group_ids" {
  description = "Azure AD group IDs for Grafana admin access"
  type        = list(string)
  default     = []
}
