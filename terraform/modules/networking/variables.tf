###############################################################################
# Networking Module - Variables
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

variable "vnet_address_space" {
  description = "Address space for the virtual network"
  type        = list(string)
}

variable "aks_subnet_prefix" {
  description = "CIDR prefix for the AKS subnet"
  type        = string
}

variable "database_subnet_prefix" {
  description = "CIDR prefix for the database subnet"
  type        = string
}

variable "monitoring_subnet_prefix" {
  description = "CIDR prefix for the monitoring subnet"
  type        = string
}

variable "gateway_subnet_prefix" {
  description = "CIDR prefix for the application gateway subnet"
  type        = string
}

variable "enable_application_gateway" {
  description = "Whether to deploy Azure Application Gateway"
  type        = bool
  default     = true
}

variable "app_gateway_sku" {
  description = "SKU tier for the Application Gateway"
  type        = string
  default     = "WAF_v2"
}
