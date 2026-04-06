###############################################################################
# Autoscaling Module
# AKS node pool autoscaler configuration, KEDA ScaledObject definitions for
# Kong proxy and admin panel, and HPA fallback configurations.
###############################################################################

terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
  }
}

# -----------------------------------------------------------------------------
# KEDA ScaledObject - Kong Proxy (request rate + latency triggers)
# -----------------------------------------------------------------------------

resource "kubernetes_manifest" "kong_proxy_scaledobject" {
  manifest = {
    apiVersion = "keda.sh/v1alpha1"
    kind       = "ScaledObject"
    metadata = {
      name      = "kong-proxy-scaler"
      namespace = "kong"
      labels = {
        app         = "kong-proxy"
        environment = var.environment
        managed_by  = "terraform"
      }
    }
    spec = {
      scaleTargetRef = {
        name = "kong-proxy"
        kind = "Deployment"
      }
      pollingInterval  = 15
      cooldownPeriod   = 60
      minReplicaCount  = var.kong_proxy_min_replicas
      maxReplicaCount  = var.kong_proxy_max_replicas
      fallback = {
        failureThreshold = 3
        replicas         = var.kong_proxy_min_replicas
      }
      triggers = [
        {
          type = "prometheus"
          metadata = {
            serverAddress = var.prometheus_server_url
            metricName    = "kong_http_requests_total_rate"
            query         = "sum(rate(kong_http_requests_total[2m]))"
            threshold     = var.kong_proxy_target_rps
          }
        },
        {
          type = "prometheus"
          metadata = {
            serverAddress = var.prometheus_server_url
            metricName    = "kong_request_latency_p95"
            query         = "histogram_quantile(0.95, sum(rate(kong_request_latency_ms_bucket[5m])) by (le))"
            threshold     = var.kong_proxy_target_latency_ms
          }
        },
      ]
      advanced = {
        horizontalPodAutoscalerConfig = {
          behavior = {
            scaleUp = {
              stabilizationWindowSeconds = 30
              policies = [
                {
                  type          = "Percent"
                  value         = 50
                  periodSeconds = 30
                },
              ]
            }
            scaleDown = {
              stabilizationWindowSeconds = 300
              policies = [
                {
                  type          = "Percent"
                  value         = 20
                  periodSeconds = 60
                },
              ]
            }
          }
        }
      }
    }
  }
}

# -----------------------------------------------------------------------------
# KEDA ScaledObject - Admin Panel (CPU + memory triggers)
# -----------------------------------------------------------------------------

resource "kubernetes_manifest" "admin_panel_scaledobject" {
  manifest = {
    apiVersion = "keda.sh/v1alpha1"
    kind       = "ScaledObject"
    metadata = {
      name      = "admin-panel-scaler"
      namespace = "kong"
      labels = {
        app         = "admin-panel"
        environment = var.environment
        managed_by  = "terraform"
      }
    }
    spec = {
      scaleTargetRef = {
        name = "admin-panel"
        kind = "Deployment"
      }
      pollingInterval  = 30
      cooldownPeriod   = 120
      minReplicaCount  = var.admin_panel_min_replicas
      maxReplicaCount  = var.admin_panel_max_replicas
      fallback = {
        failureThreshold = 3
        replicas         = var.admin_panel_min_replicas
      }
      triggers = [
        {
          type = "cpu"
          metricType = "Utilization"
          metadata = {
            value = tostring(var.admin_panel_target_cpu_percent)
          }
        },
        {
          type = "memory"
          metricType = "Utilization"
          metadata = {
            value = "80"
          }
        },
      ]
      advanced = {
        horizontalPodAutoscalerConfig = {
          behavior = {
            scaleUp = {
              stabilizationWindowSeconds = 60
              policies = [
                {
                  type          = "Pods"
                  value         = 2
                  periodSeconds = 60
                },
              ]
            }
            scaleDown = {
              stabilizationWindowSeconds = 300
              policies = [
                {
                  type          = "Pods"
                  value         = 1
                  periodSeconds = 120
                },
              ]
            }
          }
        }
      }
    }
  }
}

# -----------------------------------------------------------------------------
# Horizontal Pod Autoscaler Fallback - Kong Proxy
# Used when KEDA is unavailable or as a safety net.
# -----------------------------------------------------------------------------

resource "kubernetes_horizontal_pod_autoscaler_v2" "kong_proxy_fallback" {
  metadata {
    name      = "kong-proxy-hpa-fallback"
    namespace = "kong"
    labels = {
      app         = "kong-proxy"
      environment = var.environment
      managed_by  = "terraform"
      purpose     = "keda-fallback"
    }
  }

  spec {
    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = "kong-proxy"
    }

    min_replicas = var.kong_proxy_min_replicas
    max_replicas = var.kong_proxy_max_replicas

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 70
        }
      }
    }

    metric {
      type = "Resource"
      resource {
        name = "memory"
        target {
          type                = "Utilization"
          average_utilization = 80
        }
      }
    }

    behavior {
      scale_up {
        stabilization_window_seconds = 30
        policy {
          type           = "Percent"
          value          = 50
          period_seconds = 30
        }
      }
      scale_down {
        stabilization_window_seconds = 300
        policy {
          type           = "Percent"
          value          = 20
          period_seconds = 60
        }
      }
    }
  }
}

# -----------------------------------------------------------------------------
# Horizontal Pod Autoscaler Fallback - Admin Panel
# -----------------------------------------------------------------------------

resource "kubernetes_horizontal_pod_autoscaler_v2" "admin_panel_fallback" {
  metadata {
    name      = "admin-panel-hpa-fallback"
    namespace = "kong"
    labels = {
      app         = "admin-panel"
      environment = var.environment
      managed_by  = "terraform"
      purpose     = "keda-fallback"
    }
  }

  spec {
    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = "admin-panel"
    }

    min_replicas = var.admin_panel_min_replicas
    max_replicas = var.admin_panel_max_replicas

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = var.admin_panel_target_cpu_percent
        }
      }
    }

    behavior {
      scale_up {
        stabilization_window_seconds = 60
        policy {
          type           = "Pods"
          value          = 2
          period_seconds = 60
        }
      }
      scale_down {
        stabilization_window_seconds = 300
        policy {
          type           = "Pods"
          value          = 1
          period_seconds = 120
        }
      }
    }
  }
}

# -----------------------------------------------------------------------------
# AKS Node Pool Autoscaler Profile (cluster-level tuning)
# Note: The actual autoscaler is enabled on the node pool in the kong module.
# This resource adjusts cluster-wide autoscaler behavior.
# -----------------------------------------------------------------------------

resource "null_resource" "aks_autoscaler_profile" {
  triggers = {
    cluster_id     = var.aks_cluster_id
    min_count      = var.node_pool_min_count
    max_count      = var.node_pool_max_count
  }

  provisioner "local-exec" {
    command = <<-EOT
      az aks update \
        --resource-group ${var.resource_group_name} \
        --name ${var.aks_cluster_name} \
        --cluster-autoscaler-profile \
          scan-interval=10s \
          scale-down-delay-after-add=10m \
          scale-down-delay-after-delete=10s \
          scale-down-unneeded-time=10m \
          max-graceful-termination-sec=600 \
          balance-similar-node-groups=true \
          expander=least-waste \
          skip-nodes-with-local-storage=false \
          skip-nodes-with-system-pods=true \
          max-node-provision-time=15m
    EOT
  }
}
