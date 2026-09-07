# ==============================================================================
# GTİP Tespit - Cloud Run Jobs & Cloud Scheduler Dağıtım Betiği (PowerShell)
# ==============================================================================
$ErrorActionPreference = "Stop"

$PROJECT_ID = "gtip-tespit-projesi"
$REGION = "europe-west4"
$REPO_NAME = "gtip-repo"
$IMAGE_URI = "$($REGION)-docker.pkg.dev/$($PROJECT_ID)/$($REPO_NAME)/backend:latest"
$CLOUD_SQL_INSTANCE = "$($PROJECT_ID):europe-west4:gtip-sql-postgres-west4"
$GCS_BUCKET = "gtip-storage-west4"
$SERVICE_ACCOUNT = "gtip-backend-sa@$($PROJECT_ID).iam.gserviceaccount.com"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🚀 RESMÎ GAZETE ETL CLOUD RUN JOBS & SCHEDULER DAĞITIMI" -ForegroundColor Green
Write-Host "   Proje ID:     $PROJECT_ID"
Write-Host "   Bölge:        $REGION (Hollanda / Eemshaven)"
Write-Host "   Docker İmajı: $IMAGE_URI"
Write-Host "   Cloud SQL:    $CLOUD_SQL_INSTANCE"
Write-Host "   GCS Kova:     $GCS_BUCKET"
Write-Host "=========================================================="

# 1. 6 Yıllık Arşiv Taraması İşi (Batch Job - 2020-01-01 - 2026-08-19)
Write-Host "`n📦 [1/3] gtip-archive-backfill-job Cloud Run Job oluşturuluyor/güncelleniyor..." -ForegroundColor Yellow
gcloud run jobs create gtip-archive-backfill-job `
  --image="$IMAGE_URI" `
  --region="$REGION" `
  --project="$PROJECT_ID" `
  --tasks=1 `
  --task-timeout="86400s" `
  --memory="4Gi" `
  --cpu="2" `
  --service-account="$SERVICE_ACCOUNT" `
  --set-cloudsql-instances="$CLOUD_SQL_INSTANCE" `
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,GCS_BUCKET_NAME=$GCS_BUCKET,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,DB_USER=postgres,DB_NAME=gtip_db,EMULATOR_MODE=false" `
  --set-secrets="DB_PASS=gtip-db-password:latest,GEMINI_API_KEY=gtip-gemini-api-key:latest" `
  --command="python" `
  --args="scripts/spider_resmi_gazete_archive.py,--start-date,2020-01-01,--end-date,2026-08-19,--batch-size,30" `
  2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud run jobs update gtip-archive-backfill-job `
      --image="$IMAGE_URI" `
      --region="$REGION" `
      --project="$PROJECT_ID" `
      --tasks=1 `
      --task-timeout="86400s" `
      --memory="4Gi" `
      --cpu="2" `
      --service-account="$SERVICE_ACCOUNT" `
      --set-cloudsql-instances="$CLOUD_SQL_INSTANCE" `
      --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,GCS_BUCKET_NAME=$GCS_BUCKET,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,DB_USER=postgres,DB_NAME=gtip_db,EMULATOR_MODE=false" `
      --set-secrets="DB_PASS=gtip-db-password:latest,GEMINI_API_KEY=gtip-gemini-api-key:latest" `
      --command="python" `
      --args="scripts/spider_resmi_gazete_archive.py,--start-date,2020-01-01,--end-date,2026-08-19,--batch-size,30"
}

# 2. Günlük Gece Yarısı Senkronizasyon İşi (Daily Cron Job)
Write-Host "`n📦 [2/3] gtip-daily-sync-job Cloud Run Job oluşturuluyor/güncelleniyor..." -ForegroundColor Yellow
gcloud run jobs create gtip-daily-sync-job `
  --image="$IMAGE_URI" `
  --region="$REGION" `
  --project="$PROJECT_ID" `
  --tasks=1 `
  --task-timeout="1800s" `
  --memory="2Gi" `
  --cpu="1" `
  --service-account="$SERVICE_ACCOUNT" `
  --set-cloudsql-instances="$CLOUD_SQL_INSTANCE" `
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,GCS_BUCKET_NAME=$GCS_BUCKET,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,DB_USER=postgres,DB_NAME=gtip_db,EMULATOR_MODE=false" `
  --set-secrets="DB_PASS=gtip-db-password:latest,GEMINI_API_KEY=gtip-gemini-api-key:latest" `
  --command="python" `
  --args="scripts/spider_resmi_gazete_archive.py,--mode,daily,--days-back,2" `
  2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud run jobs update gtip-daily-sync-job `
      --image="$IMAGE_URI" `
      --region="$REGION" `
      --project="$PROJECT_ID" `
      --tasks=1 `
      --task-timeout="1800s" `
      --memory="2Gi" `
      --cpu="1" `
      --service-account="$SERVICE_ACCOUNT" `
      --set-cloudsql-instances="$CLOUD_SQL_INSTANCE" `
      --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,GCS_BUCKET_NAME=$GCS_BUCKET,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,DB_USER=postgres,DB_NAME=gtip_db,EMULATOR_MODE=false" `
      --set-secrets="DB_PASS=gtip-db-password:latest,GEMINI_API_KEY=gtip-gemini-api-key:latest" `
      --command="python" `
      --args="scripts/spider_resmi_gazete_archive.py,--mode,daily,--days-back,2"
}

# 3. Cloud Scheduler Tetikleyicisi
Write-Host "`n⏰ [3/3] gtip-daily-sync-trigger Cloud Scheduler yapılandırılıyor..." -ForegroundColor Yellow
$JOB_URI = "https://$REGION-run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/gtip-daily-sync-job:run"
try {
    gcloud scheduler jobs create http gtip-daily-sync-trigger `
      --location="$REGION" `
      --project="$PROJECT_ID" `
      --schedule="0 2 * * *" `
      --time-zone="Europe/Istanbul" `
      --uri="$JOB_URI" `
      --http-method="POST" `
      --oauth-service-account-email="$SERVICE_ACCOUNT"
} catch {
    Write-Host "Scheduler mevcut, güncelleniyor..." -ForegroundColor DarkYellow
    gcloud scheduler jobs update http gtip-daily-sync-trigger `
      --location="$REGION" `
      --project="$PROJECT_ID" `
      --schedule="0 2 * * *" `
      --time-zone="Europe/Istanbul" `
      --uri="$JOB_URI" `
      --http-method="POST" `
      --oauth-service-account-email="$SERVICE_ACCOUNT"
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "✅ TÜM JOBS & SCHEDULER BAŞARIYLA DAĞITILDI!" -ForegroundColor Green
Write-Host "   - Toplu Arşiv İşi Çalıştırma: gcloud run jobs execute gtip-archive-backfill-job --region=$REGION"
Write-Host "   - Günlük Gece İşi Çalıştırma: gcloud run jobs execute gtip-daily-sync-job --region=$REGION"
Write-Host "==========================================================" -ForegroundColor Green
