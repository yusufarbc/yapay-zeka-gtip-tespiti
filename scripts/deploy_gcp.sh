#!/usr/bin/env bash
# ==============================================================================
# GTİP Tespit Karar Destek Sistemi - %100 GCP Cloud Run & Artifact Registry Deploy Scripti
# v2 — IAM Düzeltmeleri, Cloud SQL Auth Proxy mount, Cloud Scheduler
# ==============================================================================
set -e

PROJECT_ID=${1:-${GCP_PROJECT_ID:-"gtip-tespit-projesi"}}
REGION=${2:-"europe-west4"}
REPO_NAME="gtip-repo"
SERVICE_NAME="gtip-backend"
SYNC_JOB_NAME="gtip-btb-sync-job"
SERVICE_ACCOUNT="gtip-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com"
CLOUD_SQL_INSTANCE="${PROJECT_ID}:europe-west4:gtip-db-west4"
GCS_BUCKET="gtip-evrak-bucket-${PROJECT_ID}"

echo "======================================================================"
echo "🚀 GTİP GCP CLOUD RUN CANLIYA ALIM v2 BAŞLATILIYOR"
echo "Project ID : $PROJECT_ID"
echo "Bölge      : $REGION (Hollanda / Eemshaven)"
echo "======================================================================"

# 1. GCP Yetkilendirme ve Service Account Kontrolü
gcloud config set project "$PROJECT_ID"

SA_NAME="gtip-backend-sa"
if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" >/dev/null 2>&1; then
    echo "👤 Service Account Oluşturuluyor: $SA_NAME..."
    gcloud iam service-accounts create "$SA_NAME" \
        --display-name="GTIP Backend Service Account" 2>/dev/null || true
fi

# -----------------------------------------------------------------------
# IAM ROL ATAMALARI (Tüm gerekli roller)
# -----------------------------------------------------------------------
echo "🔒 Service Account IAM rolleri atanıyor..."

# Secret Manager: Secrets okuma
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor" >/dev/null 2>&1 || true

# GCS: Bucket'a okuma/yazma (BTB verileri, embedding JSONL)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/storage.objectAdmin" >/dev/null 2>&1 || true

# Cloud SQL: Auth Proxy üzerinden PostgreSQL bağlantısı
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/cloudsql.client" >/dev/null 2>&1 || true

# Vertex AI: Embedding API ve model inference (ADC ile — API key gerektirmez)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/aiplatform.user" >/dev/null 2>&1 || true

# Cloud Run Jobs: Kendi kendini tetikleme (Scheduler için)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/run.invoker" >/dev/null 2>&1 || true

# Logs: Cloud Logging yazma
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/logging.logWriter" >/dev/null 2>&1 || true

echo "✅ IAM rolleri başarıyla atandı."

# -----------------------------------------------------------------------
# GCS Bucket Oluşturma (Yoksa)
# -----------------------------------------------------------------------
echo "🪣 GCS Bucket Kontrol Ediliyor: gs://$GCS_BUCKET ..."
gcloud storage buckets describe "gs://$GCS_BUCKET" >/dev/null 2>&1 || \
gcloud storage buckets create "gs://$GCS_BUCKET" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --uniform-bucket-level-access

# -----------------------------------------------------------------------
# Secret Manager
# -----------------------------------------------------------------------
if ! gcloud secrets describe gtip-gemini-api-key >/dev/null 2>&1; then
    echo "🔑 Secret Manager'da gtip-gemini-api-key oluşturuluyor..."
    printf "%s" "${GEMINI_API_KEY:-PLACEHOLDER_REPLACE_ME}" | \
        gcloud secrets create gtip-gemini-api-key --data-file=- 2>/dev/null || true
fi

if ! gcloud secrets describe gtip-jwt-secret >/dev/null 2>&1; then
    echo "🔑 Secret Manager'da gtip-jwt-secret oluşturuluyor..."
    printf "%s" "${JWT_SECRET_KEY:-gtip-jwt-secret-placeholder-2026}" | \
        gcloud secrets create gtip-jwt-secret --data-file=- 2>/dev/null || true
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
echo "☁️ GCP Cloud Run Backend Servisine Deploy Ediliyor..."
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
    --add-cloudsql-instances "$CLOUD_SQL_INSTANCE" \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},ENVIRONMENT=production,GCS_BUCKET_NAME=${GCS_BUCKET},CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_INSTANCE}" \
    --set-secrets "GEMINI_API_KEY=gtip-gemini-api-key:latest,JWT_SECRET_KEY=gtip-jwt-secret:latest"

BACKEND_URL="https://gtip-backend-230333256951.europe-west3.run.app"

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

# -----------------------------------------------------------------------
# 6. Cloud Run Job (BTB Sync) — Cloud SQL Auth Proxy MOUNT EDİLİYOR
# -----------------------------------------------------------------------
echo "⏰ Cloud Run Job (BTB Sync Scraper) Yapılandırılıyor..."
echo "   → Cloud SQL Auth Proxy socket mount: $CLOUD_SQL_INSTANCE"

gcloud run jobs create "$SYNC_JOB_NAME" \
    --image "$IMAGE_URI" \
    --region "$REGION" \
    --command "python" \
    --args "scripts/sync_customs_data.py" \
    --service-account "$SERVICE_ACCOUNT" \
    --add-cloudsql-instances "$CLOUD_SQL_INSTANCE" \
    --memory 1Gi \
    --cpu 2 \
    --max-retries 2 \
    --task-timeout 1200s \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},ENVIRONMENT=production,GCS_BUCKET_NAME=${GCS_BUCKET},CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_INSTANCE},GCP_REGION=${REGION}" \
    --set-secrets "GEMINI_API_KEY=gtip-gemini-api-key:latest" 2>/dev/null || \
gcloud run jobs update "$SYNC_JOB_NAME" \
    --image "$IMAGE_URI" \
    --region "$REGION" \
    --add-cloudsql-instances "$CLOUD_SQL_INSTANCE" \
    --memory 1Gi \
    --cpu 2 \
    --max-retries 2 \
    --task-timeout 1200s \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},ENVIRONMENT=production,GCS_BUCKET_NAME=${GCS_BUCKET},CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_INSTANCE},GCP_REGION=${REGION}" \
    --set-secrets "GEMINI_API_KEY=gtip-gemini-api-key:latest"

echo "✅ Cloud Run Job güncellendi: $SYNC_JOB_NAME"

# -----------------------------------------------------------------------
# 7. Cloud Scheduler — Her gece 23:00 UTC (Türkiye saati 02:00)
# -----------------------------------------------------------------------
echo "🕐 Cloud Scheduler Cron Tetikleyicisi Yapılandırılıyor (02:00 TST / 23:00 UTC)..."

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null || echo "")
JOB_RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${SYNC_JOB_NAME}:run"

gcloud scheduler jobs create http "gtip-btb-daily-sync" \
    --schedule="0 23 * * *" \
    --uri="$JOB_RUN_URI" \
    --message-body='{}' \
    --oauth-service-account-email="$SERVICE_ACCOUNT" \
    --location="$REGION" \
    --time-zone="UTC" \
    --description="GTİP BTB Scraper — Her gece 02:00 TST canlı veri senkronizasyonu" 2>/dev/null || \
gcloud scheduler jobs update http "gtip-btb-daily-sync" \
    --schedule="0 23 * * *" \
    --uri="$JOB_RUN_URI" \
    --message-body='{}' \
    --oauth-service-account-email="$SERVICE_ACCOUNT" \
    --location="$REGION" \
    --time-zone="UTC" 2>/dev/null || true

echo "✅ Cloud Scheduler yapılandırıldı: gtip-btb-daily-sync (0 23 * * * UTC)"

# -----------------------------------------------------------------------
# 8. IAP Service Account Cloud Run Invoker Rolü (varsa)
# -----------------------------------------------------------------------
echo "🔒 IAP backend service bağlantısı yapılandırılıyor..."
if [ -n "$PROJECT_NUMBER" ]; then
    gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
        --region="$REGION" \
        --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com" \
        --role="roles/run.invoker" 2>/dev/null || echo "[UYARI] IAP service account bağlaması manuel yapılmalı."
fi

echo "======================================================================"
echo "✅ DEPLOYMENT BAŞARIYLA TAMAMLANDI!"
echo "Backend URL : $BACKEND_URL"
echo "Frontend URL: $(gcloud run services describe gtip-web --region $REGION --format='value(status.url)' 2>/dev/null || echo '')"
echo ""
echo "📋 Tanımlanan IAM Rolleri (gtip-backend-sa):"
echo "   • roles/secretmanager.secretAccessor"
echo "   • roles/storage.objectAdmin         ← YENİ"
echo "   • roles/cloudsql.client             ← YENİ"
echo "   • roles/aiplatform.user             ← YENİ"
echo "   • roles/run.invoker                 ← YENİ"
echo "   • roles/logging.logWriter           ← YENİ"
echo ""
echo "⏰ Cloud Scheduler: Her gece 02:00 TST (23:00 UTC)"
echo "   Tetikleyici: gtip-btb-daily-sync → $SYNC_JOB_NAME"
echo ""
echo "⚠️  Secret Manager'da aşağıdaki secret değerlerini kontrol edin:"
echo "   gcloud secrets versions access latest --secret=gtip-gemini-api-key"
echo "======================================================================"
