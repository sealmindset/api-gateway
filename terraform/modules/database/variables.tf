###############################################################################
# Database Module - Variables
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

variable "database_subnet_id" {
  description = "ID of the database subnet"
  type        = string
}

variable "private_dns_zone_id" {
  description = "ID of the PostgreSQL private DNS zone"
  type        = string
}

variable "vnet_id" {
  description = "ID of the virtual network"
  type        = string
}

variable "postgresql_sku" {
  description = "SKU name for PostgreSQL Flexible Server"
  type        = string
}

variable "postgresql_storage_mb" {
  description = "Storage size in MB"
  type        = number
}

variable "postgresql_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15"
}

variable "administrator_login" {
  description = "Administrator login for PostgreSQL"
  type        = string
}

variable "administrator_password" {
  description = "Administrator password for PostgreSQL"
  type        = string
  sensitive   = true
}

variable "backup_retention_days" {
  description = "Number of days to retain backups"
  type        = number
  default     = 7
}

variable "geo_redundant_backup" {
  description = "Enable geo-redundant backups"
  type        = bool
  default     = false
}

variable "high_availability_enabled" {
  description = "Enable zone-redundant high availability"
  type        = bool
  default     = false
}
