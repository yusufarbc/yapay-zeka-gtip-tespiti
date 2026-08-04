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
# NOT: --no-allow-unauthenticated kullanılıyor. GCP IAP (Identity-Aware Proxy)
# üzerinden erişim kontrol edildiğinden endpoint kamuya açık olmamalıdır.
echo "☁️ GCP Cloud Run Servisine Deploy Ediliyor (IAP korumalı)..."
gcloud run deploy "$SERVICE_NAME" \
    --image "$IMAGE_URI" \
    --region "$REGION" \
    --platform managed \
    --no-allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --concurrency 80 \
    --min-instances 0 \
    --max-instances 100 \
    --timeout 300s \
    --service-account "$SERVICE_ACCOUNT" \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},ENVIRONMENT=production" \
    --set-secrets "GEMINI_API_KEY=gtip-gemini-api-key:latest,JWT_SECRET_KEY=gtip-jwt-secret:latest"

# 5. IAP Service Account Cloud Run Invoker Rolü (varsa)
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
echo "GCP Cloud Run URL'sini kontrol etmek için:"
echo "gcloud run services describe $SERVICE_NAME --region $REGION --format='value(status.url)'"
echo ""
echo "⚠️  GCP Secret Manager'da aşağıdaki secret'ların tanımlı olduğundan emin olun:"
echo "   gcloud secrets create gtip-gemini-api-key --data-file=-"
echo "   gcloud secrets create gtip-jwt-secret --data-file=-"
echo "======================================================================"
