#!/usr/bin/env bash
# ==============================================================================
# GTİP Tespit Karar Destek Sistemi - %100 GCP Cloud Run & Artifact Registry Deploy Scripti
# ==============================================================================
set -e

PROJECT_ID=${1:-${GCP_PROJECT_ID:-"gtip-tespit-projesi"}}
REGION=${2:-"europe-west3"}
REPO_NAME="gtip-repo"

echo "======================================================================"
echo "🚀 %100 GCP CLOUD RUN CANLIYA ALIM BASLATILIYOR"
echo "Project ID : $PROJECT_ID"
echo "Bölge      : $REGION (Frankfurt)"
echo "======================================================================"

# 1. GCP Yetkilendirme Kontrolü
gcloud config set project "$PROJECT_ID"

# 2. Artifact Registry Deposu Oluşturma (Yoksa)
echo "📦 Artifact Registry Deposu Kontrol Ediliyor..."
gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" >/dev/null 2>&1 || \
gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --description="GTİP Decision Support Docker Container Repository"

IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/backend:latest"

# 3. Cloud Build İle İmaj Derleme
echo "🛠️ Cloud Build İle Docker İmajı Derleniyor..."
gcloud builds submit --tag "$IMAGE_URI" .

# 4. Cloud Run Üzerinde Backend'i Canlıya Alma
echo "☁️ GCP Cloud Run Servisine Deploy Ediliyor..."
gcloud run deploy gtip-backend \
    --image "$IMAGE_URI" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars GCP_PROJECT="$PROJECT_ID",GCP_REGION="$REGION",ENVIRONMENT="production"

echo "======================================================================"
echo "✅ DEPLOYMENT BASARIYLA TAMAMLANDI!"
echo "GCP Cloud Run URL'sini kontrol etmek için:"
echo "gcloud run services describe gtip-backend --region $REGION --format='value(status.url)'"
echo "======================================================================"
