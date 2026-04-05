# Kubernetes backend — Terraform state stored as a K8s Secret in the cluster.
# The `nexus` namespace must exist before `terraform init`.
# CI creates it with: kubectl create namespace nexus --dry-run=client -o yaml | kubectl apply -f -
#
# Initialize with:
#   terraform init -backend-config="config_path=$HOME/.kube/config" -input=false

terraform {
  backend "kubernetes" {
    secret_suffix = "nexus"
    namespace     = "nexus"
    # Connection config passed via -backend-config at init time.
  }
}
