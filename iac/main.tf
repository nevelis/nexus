# Service layer — Kubernetes resources for the Nexus application.
# Reads cluster connection info from the same substrate remote state as AGAST
# (same DOKS cluster). Nexus lives in its own `nexus` namespace.

terraform {
  required_version = ">= 1.9"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
  }
}

# ── Pull substrate outputs ─────────────────────────────────────────────────────
# We only need region + cluster_id for the database firewall rule.
# Auth for the Kubernetes provider comes from the kubeconfig (see below).
data "terraform_remote_state" "substrate" {
  backend = "s3"

  config = {
    endpoint = "https://nyc3.digitaloceanspaces.com"
    bucket   = "agast-tfstate"
    key      = "substrate/terraform.tfstate"
    region   = "us-east-1"

    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    force_path_style            = true

    access_key = var.spaces_access_key
    secret_key = var.spaces_secret_key
  }
}

# ── Kubernetes provider ────────────────────────────────────────────────────────
# Auth via kubeconfig — CI runs `doctl kubernetes cluster kubeconfig save agast-dev`
# before Terraform, so ~/.kube/config is always fresh and doesn't use a token
# that can expire when the cluster is upgraded.
provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = "do-nyc3-agast-dev"
}

provider "digitalocean" {
  token = var.do_token
}

# ── HTTPS redirect middleware ──────────────────────────────────────────────────
# Namespace-scoped Traefik middleware — nexus owns this.
# cert-manager and the letsencrypt-prod ClusterIssuer are cluster-wide resources
# managed by the AGAST substrate Terraform. Nexus references them via annotation.
resource "kubernetes_manifest" "https_redirect_middleware" {
  manifest = {
    apiVersion = "traefik.io/v1alpha1"
    kind       = "Middleware"
    metadata = {
      name      = "redirect-https"
      namespace = local.namespace
    }
    spec = {
      redirectScheme = {
        scheme    = "https"
        permanent = true
      }
    }
  }
}

locals {
  namespace = "nexus"
  hostname  = "nexus.lab.amazingland.live"
  app_labels = {
    app        = "nexus"
    managed_by = "terraform"
  }
}

# ── Shared PostgreSQL cluster (lab-dev) ───────────────────────────────────────
# The DO account cannot create new database clusters (account hold).
# lab-dev is the shared dev postgres cluster — adele, agast, and mailotron all
# live here. The `nexus` database was created manually via doctl.
data "digitalocean_database_cluster" "lab_dev" {
  name = "lab-dev"
}

resource "digitalocean_database_db" "nexus" {
  cluster_id = data.digitalocean_database_cluster.lab_dev.id
  name       = "nexus"
}

# ── ConfigMap ──────────────────────────────────────────────────────────────────
resource "kubernetes_config_map" "nexus" {
  metadata {
    name      = "nexus-config"
    namespace = local.namespace
  }

  data = {
    DJANGO_SETTINGS_MODULE = "config.settings"
    DEBUG                  = "false"
    ALLOWED_HOSTS          = local.hostname
    PORT                   = "8000"
    # sentence-transformers model is baked into the image — no API key needed
    HF_HOME = "/app/.cache/huggingface"
  }
}

# ── Secret ─────────────────────────────────────────────────────────────────────
resource "kubernetes_secret" "nexus" {
  metadata {
    name      = "nexus-secrets"
    namespace = local.namespace
  }

  data = {
    SECRET_KEY = var.django_secret_key
    # Build the connection URI pointing at the nexus database on the shared lab-dev cluster.
    # The cluster URI points to `defaultdb`; replace with `nexus` + sslmode.
    DATABASE_URL = replace(
      data.digitalocean_database_cluster.lab_dev.uri,
      "/defaultdb",
      "/nexus"
    )
  }

  type = "Opaque"
}

# ── Deployment ─────────────────────────────────────────────────────────────────
resource "kubernetes_deployment" "nexus" {
  # Don't block apply while waiting for pods — image is pushed separately by CI.
  wait_for_rollout = false

  metadata {
    name      = "nexus-backend"
    namespace = local.namespace
    labels    = local.app_labels
  }

  spec {
    replicas = var.replicas

    selector {
      match_labels = { app = "nexus" }
    }

    template {
      metadata {
        labels = local.app_labels
      }

      spec {
        image_pull_secrets {
          name = "amazingland"
        }

        # Run migrations on every rollout. Idempotent — safe to run repeatedly.
        init_container {
          name              = "migrate"
          image             = var.image
          image_pull_policy = "Always"

          command = ["python", "manage.py", "migrate", "--noinput"]

          env_from {
            config_map_ref { name = kubernetes_config_map.nexus.metadata[0].name }
          }
          env_from {
            secret_ref { name = kubernetes_secret.nexus.metadata[0].name }
          }

          security_context {
            run_as_non_root            = true
            run_as_user                = 1000
            allow_privilege_escalation = false
          }
        }

        container {
          name              = "nexus"
          image             = var.image
          image_pull_policy = "Always"

          port {
            container_port = 8000
            protocol       = "TCP"
          }

          env_from {
            config_map_ref { name = kubernetes_config_map.nexus.metadata[0].name }
          }
          env_from {
            secret_ref { name = kubernetes_secret.nexus.metadata[0].name }
          }

          resources {
            requests = {
              # sentence-transformers model adds ~200MB RAM — bumped from AGAST defaults
              memory = var.memory_request
              cpu    = var.cpu_request
            }
            limits = {
              memory = var.memory_limit
              cpu    = var.cpu_limit
            }
          }

          liveness_probe {
            http_get {
              path = "/health/"
              port = 8000
            }
            initial_delay_seconds = 40
            period_seconds        = 30
            failure_threshold     = 3
          }

          readiness_probe {
            http_get {
              path = "/health/"
              port = 8000
            }
            initial_delay_seconds = 20
            period_seconds        = 10
            failure_threshold     = 3
          }

          security_context {
            run_as_non_root            = true
            run_as_user                = 1000
            allow_privilege_escalation = false
          }
        }
      }
    }
  }
}

# ── Service ────────────────────────────────────────────────────────────────────
resource "kubernetes_service" "nexus" {
  metadata {
    name      = "nexus-backend"
    namespace = local.namespace
  }

  spec {
    selector = { app = "nexus" }

    port {
      port        = 80
      target_port = 8000
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }
}

# ── Ingress (HTTP → HTTPS redirect) ───────────────────────────────────────────
resource "kubernetes_ingress_v1" "nexus_http" {
  metadata {
    name      = "nexus-http"
    namespace = local.namespace
    labels    = local.app_labels

    annotations = {
      "traefik.ingress.kubernetes.io/router.entrypoints" = "web"
      "traefik.ingress.kubernetes.io/router.middlewares" = "${local.namespace}-redirect-https@kubernetescrd"
    }
  }

  spec {
    ingress_class_name = "traefik"

    rule {
      host = local.hostname

      http {
        path {
          path      = "/"
          path_type = "Prefix"

          backend {
            service {
              name = kubernetes_service.nexus.metadata[0].name
              port { number = 80 }
            }
          }
        }
      }
    }
  }

  depends_on = [kubernetes_manifest.https_redirect_middleware]
}

# ── Ingress (HTTPS / TLS) ──────────────────────────────────────────────────────
# cert-manager picks up the cluster-issuer annotation and provisions a TLS cert
# from the letsencrypt-prod ClusterIssuer (managed by AGAST substrate Terraform).
resource "kubernetes_ingress_v1" "nexus_https" {
  metadata {
    name      = "nexus-https"
    namespace = local.namespace
    labels    = local.app_labels

    annotations = {
      "traefik.ingress.kubernetes.io/router.entrypoints" = "websecure"
      "cert-manager.io/cluster-issuer"                   = "letsencrypt-prod"
    }
  }

  spec {
    ingress_class_name = "traefik"

    tls {
      hosts       = [local.hostname]
      secret_name = "nexus-tls"
    }

    rule {
      host = local.hostname

      http {
        path {
          path      = "/"
          path_type = "Prefix"

          backend {
            service {
              name = kubernetes_service.nexus.metadata[0].name
              port { number = 80 }
            }
          }
        }
      }
    }
  }
}
