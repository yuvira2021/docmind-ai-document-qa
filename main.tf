###############################################################################
# GCP Infrastructure — RAG Document Q&A System
# Terraform: Cloud Run + Artifact Registry + Secret Manager + IAM
###############################################################################

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  # Uncomment to use GCS backend
  # backend "gcs" {
  #   bucket = "your-terraform-state-bucket"
  #   prefix = "rag-system/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ─── Variables ────────────────────────────────────────────────────────────────
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "openai_api_key" {
  description = "OpenAI API Key"
  type        = string
  sensitive   = true
}

variable "api_gateway_key" {
  description = "API Gateway authentication key"
  type        = string
  sensitive   = true
}

# ─── Enable APIs ──────────────────────────────────────────────────────────────
resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ─── Artifact Registry ────────────────────────────────────────────────────────
resource "google_artifact_registry_repository" "rag_repo" {
  location      = var.region
  repository_id = "rag-system"
  format        = "DOCKER"
  description   = "Docker images for RAG Document Q&A System"
  depends_on    = [google_project_service.services]
}

# ─── Secret Manager ───────────────────────────────────────────────────────────
resource "google_secret_manager_secret" "openai_key" {
  secret_id = "openai-api-key"
  replication { auto {} }
  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_version" "openai_key_v1" {
  secret      = google_secret_manager_secret.openai_key.id
  secret_data = var.openai_api_key
}

resource "google_secret_manager_secret" "gateway_key" {
  secret_id = "api-gateway-key"
  replication { auto {} }
}

resource "google_secret_manager_secret_version" "gateway_key_v1" {
  secret      = google_secret_manager_secret.gateway_key.id
  secret_data = var.api_gateway_key
}

# ─── Service Account ──────────────────────────────────────────────────────────
resource "google_service_account" "rag_sa" {
  account_id   = "rag-system-sa"
  display_name = "RAG System Service Account"
}

resource "google_secret_manager_secret_iam_member" "rag_sa_openai" {
  secret_id = google_secret_manager_secret.openai_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.rag_sa.email}"
}

# ─── Cloud Run: Python RAG Service ────────────────────────────────────────────
resource "google_cloud_run_v2_service" "rag_backend" {
  name     = "rag-backend"
  location = var.region

  template {
    service_account = google_service_account.rag_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/rag-system/rag-backend:latest"

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openai_key.secret_id
            version = "latest"
          }
        }
      }

      ports { container_port = 8080 }

      startup_probe {
        http_get { path = "/health" }
        initial_delay_seconds = 10
        period_seconds        = 5
        failure_threshold     = 10
      }

      liveness_probe {
        http_get { path = "/health" }
        period_seconds    = 30
        failure_threshold = 3
      }
    }
  }

  depends_on = [
    google_artifact_registry_repository.rag_repo,
    google_project_service.services,
  ]
}

# ─── Cloud Run: Node.js API Gateway ───────────────────────────────────────────
resource "google_cloud_run_v2_service" "api_gateway" {
  name     = "rag-api-gateway"
  location = var.region

  template {
    service_account = google_service_account.rag_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 20
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/rag-system/api-gateway:latest"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "RAG_SERVICE_URL"
        value = google_cloud_run_v2_service.rag_backend.uri
      }

      env {
        name = "API_GATEWAY_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gateway_key.secret_id
            version = "latest"
          }
        }
      }

      ports { container_port = 3000 }
    }
  }

  depends_on = [google_cloud_run_v2_service.rag_backend]
}

# ─── IAM: Make gateway public ─────────────────────────────────────────────────
resource "google_cloud_run_service_iam_member" "gateway_public" {
  location = var.region
  service  = google_cloud_run_v2_service.api_gateway.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ─── Outputs ──────────────────────────────────────────────────────────────────
output "gateway_url" {
  description = "API Gateway public URL"
  value       = google_cloud_run_v2_service.api_gateway.uri
}

output "rag_backend_url" {
  description = "RAG Backend internal URL"
  value       = google_cloud_run_v2_service.rag_backend.uri
}

output "docker_registry" {
  description = "Docker image registry path"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/rag-system"
}
