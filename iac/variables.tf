variable "do_token" {
  description = "DigitalOcean API token"
  type        = string
  sensitive   = true
}

variable "spaces_access_key" {
  description = "DigitalOcean Spaces access key (for reading substrate remote state)"
  type        = string
  sensitive   = true
}

variable "spaces_secret_key" {
  description = "DigitalOcean Spaces secret key"
  type        = string
  sensitive   = true
}

variable "image" {
  description = "Full container image URI (registry/name:tag)"
  type        = string
}

variable "replicas" {
  description = "Number of pod replicas"
  type        = number
  default     = 1
}

variable "django_secret_key" {
  description = "Django SECRET_KEY value"
  type        = string
  sensitive   = true
}

variable "db_size" {
  description = "DigitalOcean managed database size slug"
  type        = string
  default     = "db-s-1vcpu-1gb"  # 1 vCPU, 1 GiB RAM — $15/mo
}

variable "memory_request" {
  description = "Pod memory request — bumped vs AGAST defaults due to sentence-transformers model (~200MB)"
  type        = string
  default     = "512Mi"
}

variable "cpu_request" {
  type    = string
  default = "250m"
}

variable "memory_limit" {
  description = "Pod memory limit"
  type        = string
  default     = "1Gi"
}

variable "cpu_limit" {
  type    = string
  default = "500m"
}

variable "letsencrypt_email" {
  description = "Email for Let's Encrypt certificate registration and expiry notifications"
  type        = string
  default     = "nevelis@gmail.com"
}
