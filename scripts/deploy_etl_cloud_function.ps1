$PROJECT_ID = 'gumruk-mevzuat'
$REGION = 'us-central1'
$FUNCTION_NAME = 'resmi-gazete-crawler'
$SERVICE_ACCOUNT = "gtip-backend-sa@$PROJECT_ID.iam.gserviceaccount.com"

Write-Host "=========================================================="
Write-Host "  RESMI GAZETE RADARI CLOUD FUNCTION (2nd Gen) DEPLOY"
Write-Host "=========================================================="
gcloud.cmd config set project $PROJECT_ID
gcloud.cmd config set compute/region $REGION

# 1. Cloud Function Dağıtımı
Write-Host "  1. Cloud Run Function dağıtılıyor ($REGION)..."
gcloud.cmd functions deploy $FUNCTION_NAME `
    --gen2 `
    --runtime python311 `
    --region $REGION `
    --source . `
    --entry-point main_cloud_function `
    --trigger-http `
    --no-allow-unauthenticated `
    --service-account $SERVICE_ACCOUNT `
    --memory 1024MB `
    --timeout 540s `
    --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,EMBEDDING_MODEL=text-embedding-005"

if ($LASTEXITCODE -ne 0) { Write-Error "Function deploy hatası!"; exit 1 }

$FUNCTION_URI = gcloud.cmd functions describe $FUNCTION_NAME --region $REGION --format="value(serviceConfig.uri)"

# 2. Cloud Scheduler Zamanlayıcısı (Her gece 02:00)
Write-Host "  2. Cloud Scheduler CRON (0 2 * * *) ayarlanıyor..."
gcloud.cmd scheduler jobs create http resmi-gazete-daily-trigger `
    --location $REGION `
    --schedule "0 2 * * *" `
    --time-zone "Europe/Istanbul" `
    --uri $FUNCTION_URI `
    --http-method POST `
    --oidc-service-account-email $SERVICE_ACCOUNT 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "  Mevcut Cloud Scheduler görevi güncelleniyor..."
    gcloud.cmd scheduler jobs update http resmi-gazete-daily-trigger `
        --location $REGION `
        --schedule "0 2 * * *" `
        --time-zone "Europe/Istanbul" `
        --uri $FUNCTION_URI `
        --http-method POST `
        --oidc-service-account-email $SERVICE_ACCOUNT 2>$null
}

Write-Host "=========================================================="
Write-Host "  ETL RADARI BAŞARIYLA CANLIYA ALINDI!"
Write-Host "  Zamanlama: Her gece 02:00 (Europe/Istanbul)"
Write-Host "=========================================================="
