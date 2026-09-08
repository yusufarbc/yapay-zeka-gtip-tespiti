$PROJECT_ID = 'gumruk-mevzuat'
$REGION = 'us-central1'
$REPO_NAME = 'gtip-repo'
$JOB_NAME = 'gtip-archive-backfill'
$IMAGE_URI = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/backend:latest"
$CLOUD_SQL_INSTANCE = 'gumruk-mevzuat:us-central1:gumruk-db'
$GCS_BUCKET = 'gumruk-mevzuat-storage-us-central1'
$SERVICE_ACCOUNT = "gtip-backend-sa@$PROJECT_ID.iam.gserviceaccount.com"
$ErrorActionPreference = 'Stop'

Write-Host "=========================================================="
Write-Host "  DEPLOYING CLOUD RUN JOB: $JOB_NAME ($PROJECT_ID)"
Write-Host "=========================================================="

# 1. Config ayarları
& "gcloud.cmd" config set project $PROJECT_ID
& "gcloud.cmd" config set compute/region $REGION

# 2. Secret Manager kontrolü. Parola bu betikte asla üretilmez veya kaynak koda yazılmaz.
Write-Host "  Secret Manager kontrol ediliyor (gtip-db-password)..."
$secretCheck = & "gcloud.cmd" secrets describe gtip-db-password --project $PROJECT_ID 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "gtip-db-password Secret Manager'da bulunamadı. Cloud SQL parolasıyla aynı değeri güvenli bir kanaldan secret olarak oluşturun."
}

# 3. Cloud Run Job Oluştur / Güncelle
Write-Host "  Cloud Run Job kontrol ediliyor: $JOB_NAME..."
$jobExists = & "gcloud.cmd" run jobs describe $JOB_NAME --region $REGION 2>&1

$ENV_VARS = "GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,ENVIRONMENT=production,PRIMARY_AI_MODEL=gemini-2.5-flash,EXTRACTOR_LLM_MODEL=gemini-2.5-flash-lite,REASONING_LLM_MODEL=gemini-2.5-flash,EMBEDDING_MODEL=text-embedding-005,GCS_BUCKET_NAME=$GCS_BUCKET,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,DB_USER=postgres,DB_NAME=gtip_db,EMULATOR_MODE=false"

if ($LASTEXITCODE -eq 0) {
    Write-Host "  Mevcut Cloud Run Job güncelleniyor..."
    & "gcloud.cmd" run jobs update $JOB_NAME `
        --image $IMAGE_URI `
        --region $REGION `
        --project $PROJECT_ID `
        --command "python" `
        --args "scripts/spider_resmi_gazete_archive.py,--mode,archive" `
        --max-retries 3 `
        --task-timeout 86400s `
        --memory 4Gi `
        --cpu 2 `
        --service-account $SERVICE_ACCOUNT `
        --set-cloudsql-instances $CLOUD_SQL_INSTANCE `
        --set-env-vars $ENV_VARS `
        --set-secrets "DB_PASS=gtip-db-password:latest"
} else {
    Write-Host "  Yeni Cloud Run Job oluşturuluyor: $JOB_NAME..."
    & "gcloud.cmd" run jobs create $JOB_NAME `
        --image $IMAGE_URI `
        --region $REGION `
        --project $PROJECT_ID `
        --command "python" `
        --args "scripts/spider_resmi_gazete_archive.py,--mode,archive" `
        --max-retries 3 `
        --task-timeout 86400s `
        --memory 4Gi `
        --cpu 2 `
        --service-account $SERVICE_ACCOUNT `
        --set-cloudsql-instances $CLOUD_SQL_INSTANCE `
        --set-env-vars $ENV_VARS `
        --set-secrets "DB_PASS=gtip-db-password:latest"
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "Cloud Run Job oluşturma/güncelleme hatası!"
    exit 1
}

Write-Host "=========================================================="
Write-Host "  ✅ Cloud Run Job $JOB_NAME başarıyla hazırlandı!"
Write-Host "  İşi tetiklemek için:"
Write-Host "    gcloud run jobs execute $JOB_NAME --region $REGION"
Write-Host "=========================================================="
