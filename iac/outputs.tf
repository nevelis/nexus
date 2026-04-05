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

output "db_cluster" {
  description = "Shared Postgres cluster hosting the nexus database"
  value       = data.digitalocean_database_cluster.lab_dev.name
}

output "db_name" {
  description = "Database name within the shared cluster"
  value       = digitalocean_database_db.nexus.name
}
