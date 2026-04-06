###############################################################################
# Autoscaling Module - Variables
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

variable "aks_cluster_id" {
  description = "ID of the AKS cluster"
  type        = string
}

variable "aks_cluster_name" {
  description = "Name of the AKS cluster"
  type        = string
}

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
  description = "Target requests per second per pod for Kong proxy KEDA trigger"
  type        = string
  default     = "1000"
}

variable "kong_proxy_target_latency_ms" {
  description = "Target p95 latency in ms for Kong proxy KEDA trigger"
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
  description = "Target CPU utilisation percentage for admin panel"
  type        = number
  default     = 70
}

variable "prometheus_server_url" {
  description = "URL of the Prometheus server for KEDA triggers"
  type        = string
}

variable "node_pool_min_count" {
  description = "Minimum node count for AKS node pool autoscaler"
  type        = number
}

variable "node_pool_max_count" {
  description = "Maximum node count for AKS node pool autoscaler"
  type        = number
}
