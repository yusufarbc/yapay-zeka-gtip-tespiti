$ErrorActionPreference = "Stop"

$PROJECT_ID = "gumruk-mevzuat"
$REGION = "us-central1"
$JOB_NAME = "gtip-seed-tgtc-2026"
$IMAGE_URI = "$REGION-docker.pkg.dev/$PROJECT_ID/gtip-repo/backend:latest"
$CLOUD_SQL_INSTANCE = "$PROJECT_ID`:$REGION`:gumruk-db"
$SERVICE_ACCOUNT = "gtip-backend-sa@$PROJECT_ID.iam.gserviceaccount.com"
$ENV_VARS = "GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,ENVIRONMENT=production,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,DB_USER=postgres,DB_NAME=gtip_db,DB_POOL_SIZE=1,DB_MAX_OVERFLOW=1,USE_GCP_EMULATOR=false,SKIP_TGTC_AUTO_SEED=true"

$existing = & gcloud.cmd run jobs list `
    --region $REGION `
    --project $PROJECT_ID `
    --filter="metadata.name=$JOB_NAME" `
    --format="value(metadata.name)"
if ($LASTEXITCODE -ne 0) { throw "Cloud Run Job listesi okunamadı." }
$action = if (($existing | Out-String).Trim()) { "update" } else { "create" }

& gcloud.cmd run jobs $action $JOB_NAME `
    --image $IMAGE_URI `
    --region $REGION `
    --project $PROJECT_ID `
    --tasks 1 `
    --max-retries 1 `
    --task-timeout 3600s `
    --memory 4Gi `
    --cpu 2 `
    --service-account $SERVICE_ACCOUNT `
    --set-cloudsql-instances $CLOUD_SQL_INSTANCE `
    --set-env-vars $ENV_VARS `
    --set-secrets "DB_PASS=gtip-db-password:latest" `
    --command python `
    "--args=scripts/seed_tgtc_2026.py" `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "2026 TGTC seed işi dağıtılamadı." }

Write-Host "Hazır: $JOB_NAME. Yıllık TGTC dosyaları güncellendikten sonra bu işi kontrollü olarak çalıştırın."
