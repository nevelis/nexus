output "namespace" {
  value = local.namespace
}

output "deployment_name" {
  value = kubernetes_deployment.nexus.metadata[0].name
}

output "service_name" {
  value = kubernetes_service.nexus.metadata[0].name
}

output "url" {
  description = "Application URL — HTTPS enforced; cert issued by Let's Encrypt via cert-manager"
  value       = "https://${local.hostname}"
}

output "mcp_endpoint" {
  description = "MCP server endpoint for agent clients (e.g. Adele)"
  value       = "https://${local.hostname}/mcp/"
}

output "db_host" {
  description = "Managed PostgreSQL host"
  value       = digitalocean_database_cluster.postgres.host
}

output "db_port" {
  description = "Managed PostgreSQL port"
  value       = digitalocean_database_cluster.postgres.port
}

output "db_name" {
  description = "Default database name"
  value       = digitalocean_database_cluster.postgres.database
}

output "db_user" {
  description = "Default database user"
  value       = digitalocean_database_cluster.postgres.user
}
