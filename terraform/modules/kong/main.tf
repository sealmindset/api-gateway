###############################################################################
# Kong Module
# AKS cluster, Azure Container Registry, Key Vault, Redis Cache,
# and managed identities for running Kong API Gateway and admin panel.
###############################################################################

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "azurerm_client_config" "current" {}

# -----------------------------------------------------------------------------
# User-Assigned Managed Identity (for AKS workloads)
# -----------------------------------------------------------------------------

resource "azurerm_user_assigned_identity" "aks_workload" {
  name                = "${var.name_prefix}-aks-workload-id"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_user_assigned_identity" "aks_kubelet" {
  name                = "${var.name_prefix}-aks-kubelet-id"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

# -----------------------------------------------------------------------------
# AKS Cluster
# -----------------------------------------------------------------------------

resource "azurerm_kubernetes_cluster" "main" {
  name                = "${var.name_prefix}-aks"
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = "${var.name_prefix}-aks"
  kubernetes_version  = var.kubernetes_version
  tags                = var.tags

  default_node_pool {
    name                = "system"
    vm_size             = var.aks_vm_size
    node_count          = var.aks_default_node_pool_size
    min_count           = var.aks_default_node_pool_min
    max_count           = var.aks_default_node_pool_max
    enable_auto_scaling = true
    vnet_subnet_id      = var.aks_subnet_id
    os_disk_size_gb     = 128
    os_disk_type        = "Managed"
    max_pods            = 110
    zones               = ["1", "2", "3"]

    node_labels = {
      "role" = "system"
    }
  }

  identity {
    type                      = "UserAssigned"
    identity_ids              = [azurerm_user_assigned_identity.aks_workload.id]
  }

  kubelet_identity {
    client_id                 = azurerm_user_assigned_identity.aks_kubelet.client_id
    object_id                 = azurerm_user_assigned_identity.aks_kubelet.principal_id
    user_assigned_identity_id = azurerm_user_assigned_identity.aks_kubelet.id
  }

  network_profile {
    network_plugin    = "azure"
    network_policy    = "calico"
    load_balancer_sku = "standard"
    service_cidr      = "172.16.0.0/16"
    dns_service_ip    = "172.16.0.10"
  }

  oms_agent {
    log_analytics_workspace_id = var.log_analytics_workspace_id
  }

  azure_active_directory_role_based_access_control {
    managed                = true
    azure_rbac_enabled     = true
  }

  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "5m"
  }

  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  maintenance_window {
    allowed {
      day   = "Sunday"
      hours = [0, 1, 2, 3, 4]
    }
  }

  lifecycle {
    ignore_changes = [
      default_node_pool[0].node_count,
    ]
  }
}

# Kong workload node pool (dedicated for Kong proxy pods)
resource "azurerm_kubernetes_cluster_node_pool" "kong" {
  name                  = "kong"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = var.aks_vm_size
  node_count            = var.aks_default_node_pool_size
  min_count             = var.aks_default_node_pool_min
  max_count             = var.aks_default_node_pool_max
  enable_auto_scaling   = true
  vnet_subnet_id        = var.aks_subnet_id
  os_disk_size_gb       = 128
  max_pods              = 60
  zones                 = ["1", "2", "3"]
  tags                  = var.tags

  node_labels = {
    "role"    = "kong"
    "workload" = "api-gateway"
  }

  node_taints = [
    "workload=kong:NoSchedule"
  ]

  lifecycle {
    ignore_changes = [
      node_count,
    ]
  }
}

# -----------------------------------------------------------------------------
# Azure Container Registry
# -----------------------------------------------------------------------------

resource "azurerm_container_registry" "main" {
  name                = replace("${var.name_prefix}acr", "-", "")
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "Premium"
  admin_enabled       = false
  tags                = var.tags

  retention_policy {
    days    = 30
    enabled = true
  }

  network_rule_set {
    default_action = "Deny"
    virtual_network {
      action    = "Allow"
      subnet_id = var.aks_subnet_id
    }
  }

  georeplications {
    location                = "westus2"
    zone_redundancy_enabled = true
    tags                    = var.tags
  }
}

# Allow AKS kubelet identity to pull images from ACR
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.aks_kubelet.principal_id
}

# -----------------------------------------------------------------------------
# Key Vault
# -----------------------------------------------------------------------------

resource "azurerm_key_vault" "main" {
  name                          = "${var.name_prefix}-kv"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  soft_delete_retention_days    = 90
  purge_protection_enabled      = true
  public_network_access_enabled = false
  enable_rbac_authorization     = true
  tags                          = var.tags

  network_acls {
    default_action             = "Deny"
    bypass                     = "AzureServices"
    virtual_network_subnet_ids = [var.aks_subnet_id]
  }
}

# Allow AKS workload identity to read secrets
resource "azurerm_role_assignment" "aks_kv_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.aks_workload.principal_id
}

# Store database credentials in Key Vault
resource "azurerm_key_vault_secret" "kong_db_host" {
  name         = "kong-db-host"
  value        = var.kong_db_host
  key_vault_id = azurerm_key_vault.main.id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "kong_db_name" {
  name         = "kong-db-name"
  value        = var.kong_db_name
  key_vault_id = azurerm_key_vault.main.id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "kong_db_user" {
  name         = "kong-db-user"
  value        = var.kong_db_user
  key_vault_id = azurerm_key_vault.main.id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "kong_db_password" {
  name         = "kong-db-password"
  value        = var.kong_db_password
  key_vault_id = azurerm_key_vault.main.id
  tags         = var.tags
}

# -----------------------------------------------------------------------------
# Azure Redis Cache
# -----------------------------------------------------------------------------

resource "azurerm_redis_cache" "main" {
  name                          = "${var.name_prefix}-redis"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  capacity                      = var.redis_capacity
  family                        = var.redis_family
  sku_name                      = var.redis_sku
  public_network_access_enabled = false
  minimum_tls_version           = "1.2"
  enable_non_ssl_port           = false
  tags                          = var.tags

  redis_configuration {
    maxmemory_policy       = "allkeys-lru"
    maxmemory_reserved     = 50
    maxfragmentationmemory_reserved = 50
  }
}

resource "azurerm_private_endpoint" "redis" {
  name                = "${var.name_prefix}-redis-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.aks_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "${var.name_prefix}-redis-psc"
    private_connection_resource_id = azurerm_redis_cache.main.id
    subresource_names              = ["redisCache"]
    is_manual_connection           = false
  }
}

# Store Redis connection info in Key Vault
resource "azurerm_key_vault_secret" "redis_host" {
  name         = "redis-host"
  value        = azurerm_redis_cache.main.hostname
  key_vault_id = azurerm_key_vault.main.id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "redis_key" {
  name         = "redis-primary-key"
  value        = azurerm_redis_cache.main.primary_access_key
  key_vault_id = azurerm_key_vault.main.id
  tags         = var.tags
}
