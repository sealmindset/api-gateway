###############################################################################
# Networking Module - Outputs
###############################################################################

output "vnet_id" {
  description = "ID of the virtual network"
  value       = azurerm_virtual_network.main.id
}

output "vnet_name" {
  description = "Name of the virtual network"
  value       = azurerm_virtual_network.main.name
}

output "aks_subnet_id" {
  description = "ID of the AKS subnet"
  value       = azurerm_subnet.aks.id
}

output "database_subnet_id" {
  description = "ID of the database subnet"
  value       = azurerm_subnet.database.id
}

output "monitoring_subnet_id" {
  description = "ID of the monitoring subnet"
  value       = azurerm_subnet.monitoring.id
}

output "gateway_subnet_id" {
  description = "ID of the application gateway subnet"
  value       = azurerm_subnet.gateway.id
}

output "postgresql_private_dns_zone_id" {
  description = "ID of the PostgreSQL private DNS zone"
  value       = azurerm_private_dns_zone.postgresql.id
}

output "redis_private_dns_zone_id" {
  description = "ID of the Redis private DNS zone"
  value       = azurerm_private_dns_zone.redis.id
}

output "keyvault_private_dns_zone_id" {
  description = "ID of the Key Vault private DNS zone"
  value       = azurerm_private_dns_zone.keyvault.id
}

output "gateway_public_ip" {
  description = "Public IP address of the Application Gateway"
  value       = var.enable_application_gateway ? azurerm_public_ip.gateway[0].ip_address : null
}

output "gateway_fqdn" {
  description = "FQDN of the Application Gateway public IP"
  value       = var.enable_application_gateway ? azurerm_public_ip.gateway[0].fqdn : null
}
