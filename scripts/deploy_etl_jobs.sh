#!/usr/bin/env bash
# ==============================================================================
# GTİP Tespit - Cloud Run Jobs & Cloud Scheduler Dağıtım Betiği (europe-west4)
# ==============================================================================
set -e

PROJECT_ID="gtip-tespit-projesi"
REGION="europe-west4"
REPO_NAME="gtip-repo"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/backend:latest"
CLOUD_SQL_INSTANCE="${PROJECT_ID}:europe-west4:gtip-db-west4"
GCS_BUCKET="gtip-storage-west4"
SERVICE_ACCOUNT="gtip-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com"

echo "======================================================================"
echo "🚀 RESMÎ GAZETE ETL CLOUD RUN JOBS & SCHEDULER DAĞITIMI BAŞLATILIYOR"
echo "   Proje ID:           ${PROJECT_ID}"
echo "   Bölge:              ${REGION} (Eemshaven / Hollanda)"
echo "   Docker İmajı:       ${IMAGE_URI}"
echo "   Cloud SQL:          ${CLOUD_SQL_INSTANCE}"
echo "   GCS Kova:           ${GCS_BUCKET}"
echo "======================================================================"

# 1. 6 Yıllık Arşiv Taraması İşi (Batch Job - 2020-01-01 - 2026-08-19)
echo "📦 [1/3] gtip-archive-backfill-job Cloud Run Job oluşturuluyor..."
gcloud run jobs create gtip-archive-backfill-job \
  --image="${IMAGE_URI}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --tasks=1 \
  --task-timeout=86400s \
  --memory="4Gi" \
  --cpu="2" \
  --service-account="${SERVICE_ACCOUNT}" \
  --set-cloudsql-instances="${CLOUD_SQL_INSTANCE}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},GCS_BUCKET_NAME=${GCS_BUCKET},CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_INSTANCE},DB_USER=postgres,DB_NAME=gtip_db,EMULATOR_MODE=false" \
  --set-secrets="DB_PASS=gtip-db-password:latest,GEMINI_API_KEY=gtip-gemini-api-key:latest" \
  --command="python" \
  --args="scripts/spider_resmi_gazete_archive.py,--start-date,2020-01-01,--end-date,2026-08-19,--batch-size,30" \
  || gcloud run jobs update gtip-archive-backfill-job \
  --image="${IMAGE_URI}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --tasks=1 \
  --task-timeout=86400s \
  --memory="4Gi" \
  --cpu="2" \
  --service-account="${SERVICE_ACCOUNT}" \
  --set-cloudsql-instances="${CLOUD_SQL_INSTANCE}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},GCS_BUCKET_NAME=${GCS_BUCKET},CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_INSTANCE},DB_USER=postgres,DB_NAME=gtip_db,EMULATOR_MODE=false" \
  --set-secrets="DB_PASS=gtip-db-password:latest,GEMINI_API_KEY=gtip-gemini-api-key:latest" \
  --command="python" \
  --args="scripts/spider_resmi_gazete_archive.py,--start-date,2020-01-01,--end-date,2026-08-19,--batch-size,30"

# 2. Günlük Gece Yarısı Senkronizasyon İşi (Daily Cron Job)
echo "📦 [2/3] gtip-daily-sync-job Cloud Run Job oluşturuluyor..."
gcloud run jobs create gtip-daily-sync-job \
  --image="${IMAGE_URI}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --tasks=1 \
  --task-timeout=1800s \
  --memory="2Gi" \
  --cpu="1" \
  --service-account="${SERVICE_ACCOUNT}" \
  --set-cloudsql-instances="${CLOUD_SQL_INSTANCE}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},GCS_BUCKET_NAME=${GCS_BUCKET},CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_INSTANCE},DB_USER=postgres,DB_NAME=gtip_db,EMULATOR_MODE=false" \
  --set-secrets="DB_PASS=gtip-db-password:latest,GEMINI_API_KEY=gtip-gemini-api-key:latest" \
  --command="python" \
  --args="scripts/spider_resmi_gazete_archive.py,--mode,daily,--days-back,2" \
  || gcloud run jobs update gtip-daily-sync-job \
  --image="${IMAGE_URI}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --tasks=1 \
  --task-timeout=1800s \
  --memory="2Gi" \
  --cpu="1" \
  --service-account="${SERVICE_ACCOUNT}" \
  --set-cloudsql-instances="${CLOUD_SQL_INSTANCE}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},GCS_BUCKET_NAME=${GCS_BUCKET},CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_INSTANCE},DB_USER=postgres,DB_NAME=gtip_db,EMULATOR_MODE=false" \
  --set-secrets="DB_PASS=gtip-db-password:latest,GEMINI_API_KEY=gtip-gemini-api-key:latest" \
  --command="python" \
  --args="scripts/spider_resmi_gazete_archive.py,--mode,daily,--days-back,2"

# 3. Cloud Scheduler Tetikleyicisi (Her Gece 02:00 Europe/Istanbul)
echo "⏰ [3/3] gtip-daily-sync-trigger Cloud Scheduler işi yapılandırılıyor..."
JOB_URI="https://${REGION}-run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/gtip-daily-sync-job:run"

gcloud scheduler jobs create http gtip-daily-sync-trigger \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --schedule="0 2 * * *" \
  --time-zone="Europe/Istanbul" \
  --uri="${JOB_URI}" \
  --http-method=POST \
  --oauth-service-account-email="${SERVICE_ACCOUNT}" \
  || gcloud scheduler jobs update http gtip-daily-sync-trigger \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --schedule="0 2 * * *" \
  --time-zone="Europe/Istanbul" \
  --uri="${JOB_URI}" \
  --http-method=POST \
  --oauth-service-account-email="${SERVICE_ACCOUNT}"

echo "======================================================================"
echo "✅ ETL CLOUD RUN JOBS VE SCHEDULER BAŞARIYLA DAĞITILDI!"
echo "   - Toplu Arşiv İşi:       gcloud run jobs execute gtip-archive-backfill-job --region=${REGION}"
echo "   - Günlük Gece İşi:       gcloud run jobs execute gtip-daily-sync-job --region=${REGION}"
echo "======================================================================"
