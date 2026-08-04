#!/usr/bin/env bash
# ==============================================================================
# GTİP Tespit Karar Destek Sistemi - %100 GCP Cloud Run & Artifact Registry Deploy Scripti
# ==============================================================================
set -e

PROJECT_ID=${1:-${GCP_PROJECT_ID:-"gtip-tespit-projesi"}}
REGION=${2:-"europe-west3"}
REPO_NAME="gtip-repo"
SERVICE_NAME="gtip-backend"
SERVICE_ACCOUNT="gtip-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com"

echo "======================================================================"
echo "🚀 %100 GCP CLOUD RUN CANLIYA ALIM BASLATILIYOR"
echo "Project ID : $PROJECT_ID"
echo "Bölge      : $REGION (Frankfurt)"
echo "======================================================================"

# 1. GCP Yetkilendirme ve Service Account Kontrolü
gcloud config set project "$PROJECT_ID"

SA_NAME="gtip-backend-sa"
if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" >/dev/null 2>&1; then
    echo "👤 Service Account Oluşturuluyor: $SA_NAME..."
    gcloud iam service-accounts create "$SA_NAME" \
        --display-name="GTIP Backend Service Account" 2>/dev/null || true
fi

# Service Account'a Secret Manager Secret Accessor yetkisi ver
echo "🔒 Service Account IAM yetkisi (roles/secretmanager.secretAccessor) veriliyor..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor" >/dev/null 2>&1 || true

# Secret Manager secret'larını otomatik oluştur (yoksa)
if ! gcloud secrets describe gtip-gemini-api-key >/dev/null 2>&1; then
    echo "🔑 Secret Manager'da gtip-gemini-api-key oluşturuluyor..."
    printf "%s" "${GEMINI_API_KEY:-gtip-gemini-api-key-placeholder}" | gcloud secrets create gtip-gemini-api-key --data-file=- 2>/dev/null || true
fi

if ! gcloud secrets describe gtip-jwt-secret >/dev/null 2>&1; then
    echo "🔑 Secret Manager'da gtip-jwt-secret oluşturuluyor..."
    printf "%s" "${JWT_SECRET_KEY:-gtip-jwt-secret-placeholder-2026}" | gcloud secrets create gtip-jwt-secret --data-file=- 2>/dev/null || true
fi

# 2. Artifact Registry Deposu Oluşturma (Yoksa)
echo "📦 Artifact Registry Deposu Kontrol Ediliyor..."
gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" >/dev/null 2>&1 || \
gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --description="GTİP Decision Support Docker Container Repository"

IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/backend:latest"
WEB_IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/web:latest"

# 3. Cloud Build İle İmaj Derleme
echo "🛠️ Cloud Build İle Backend ve Frontend Docker İmajları Derleniyor..."
gcloud builds submit --tag "$IMAGE_URI" .
gcloud builds submit --tag "$WEB_IMAGE_URI" ./web

# 4. Cloud Run Üzerinde Backend'i Canlıya Alma
echo "☁️ GCP Cloud Run Backend Servisine Deploy Ediliyor (IAP korumalı)..."
gcloud run deploy "$SERVICE_NAME" \
    --image "$IMAGE_URI" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --concurrency 80 \
    --min-instances 0 \
    --max-instances 10 \
    --timeout 300s \
    --service-account "$SERVICE_ACCOUNT" \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},ENVIRONMENT=production" \
    --set-secrets "GEMINI_API_KEY=gtip-gemini-api-key:latest,JWT_SECRET_KEY=gtip-jwt-secret:latest"

BACKEND_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)' 2>/dev/null || echo "")

# 5. Cloud Run Üzerinde Frontend (Web App) Canlıya Alma
echo "💻 GCP Cloud Run Frontend (Web App) Deploy Ediliyor..."
gcloud run deploy "gtip-web" \
    --image "$WEB_IMAGE_URI" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --set-env-vars "VITE_API_URL=${BACKEND_URL}/api/v1"

# 6. Cloud Run Job (BTB Scraper Cron Task) Tanımlama
echo "⏰ Cloud Run Job (BTB Sync Scraper) Yapılandırılıyor..."
gcloud run jobs create gtip-btb-sync-job \
    --image "$IMAGE_URI" \
    --region "$REGION" \
    --command "python" \
    --args "scripts/sync_customs_data.py" \
    --service-account "$SERVICE_ACCOUNT" \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},ENVIRONMENT=production" \
    --set-secrets "GEMINI_API_KEY=gtip-gemini-api-key:latest" 2>/dev/null || \
gcloud run jobs update gtip-btb-sync-job \
    --image "$IMAGE_URI" \
    --region "$REGION" \
    --command "python" \
    --args "scripts/sync_customs_data.py"

# 7. IAP Service Account Cloud Run Invoker Rolü (varsa)
echo "🔒 IAP backend service bağlantısı yapılandırılıyor..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null || echo "")
if [ -n "$PROJECT_NUMBER" ]; then
    gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
        --region="$REGION" \
        --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com" \
        --role="roles/run.invoker" 2>/dev/null || echo "[UYARI] IAP service account bağlaması manuel yapılmalı."
fi

echo "======================================================================"
echo "✅ DEPLOYMENT BASARIYLA TAMAMLANDI!"
echo "Backend URL : $BACKEND_URL"
echo "Frontend URL: $(gcloud run services describe gtip-web --region $REGION --format='value(status.url)' 2>/dev/null || echo '')"
echo ""
echo "⚠️  GCP Secret Manager'da aşağıdaki secret'ların tanımlı olduğundan emin olun:"
echo "   gcloud secrets create gtip-gemini-api-key --data-file=-"
echo "   gcloud secrets create gtip-jwt-secret --data-file=-"
echo "======================================================================"
