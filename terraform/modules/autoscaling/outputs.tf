###############################################################################
# Autoscaling Module - Outputs
###############################################################################

output "kong_proxy_scaledobject_name" {
  description = "Name of the Kong proxy KEDA ScaledObject"
  value       = kubernetes_manifest.kong_proxy_scaledobject.manifest.metadata.name
}

output "admin_panel_scaledobject_name" {
  description = "Name of the admin panel KEDA ScaledObject"
  value       = kubernetes_manifest.admin_panel_scaledobject.manifest.metadata.name
}

output "kong_proxy_hpa_name" {
  description = "Name of the Kong proxy fallback HPA"
  value       = kubernetes_horizontal_pod_autoscaler_v2.kong_proxy_fallback.metadata[0].name
}

output "admin_panel_hpa_name" {
  description = "Name of the admin panel fallback HPA"
  value       = kubernetes_horizontal_pod_autoscaler_v2.admin_panel_fallback.metadata[0].name
}

output "autoscaler_config" {
  description = "Summary of autoscaling configuration"
  value = {
    kong_proxy = {
      min_replicas = var.kong_proxy_min_replicas
      max_replicas = var.kong_proxy_max_replicas
      target_rps   = var.kong_proxy_target_rps
    }
    admin_panel = {
      min_replicas   = var.admin_panel_min_replicas
      max_replicas   = var.admin_panel_max_replicas
      target_cpu_pct = var.admin_panel_target_cpu_percent
    }
    node_pool = {
      min_count = var.node_pool_min_count
      max_count = var.node_pool_max_count
    }
  }
}
