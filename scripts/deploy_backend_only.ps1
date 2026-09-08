$ErrorActionPreference = "Stop"

$PROJECT_ID = "gumruk-mevzuat"
$REGION = "us-central1"
$IMAGE_URI = "$REGION-docker.pkg.dev/$PROJECT_ID/gtip-repo/backend:latest"
$CLOUD_SQL_INSTANCE = "$PROJECT_ID`:$REGION`:gumruk-db"
$GCS_BUCKET = "gumruk-mevzuat-storage-us-central1"
$SERVICE_ACCOUNT = "gtip-backend-sa@$PROJECT_ID.iam.gserviceaccount.com"
$WEB_ORIGIN = "https://gtip-web-gu6pxpqefa-uc.a.run.app"

& gcloud.cmd secrets describe gtip-db-password --project $PROJECT_ID *> $null
if ($LASTEXITCODE -ne 0) { throw "gtip-db-password Secret Manager'da bulunamadı." }
& gcloud.cmd secrets describe gtip-jwt-secret --project $PROJECT_ID *> $null
if ($LASTEXITCODE -ne 0) { throw "gtip-jwt-secret Secret Manager'da bulunamadı." }

Write-Host "Backend image derleniyor: $IMAGE_URI"
& gcloud.cmd builds submit --tag $IMAGE_URI --project $PROJECT_ID .
if ($LASTEXITCODE -ne 0) { throw "Backend Cloud Build başarısız." }

Write-Host "Backend Cloud Run'a dağıtılıyor..."
& gcloud.cmd run deploy gtip-backend `
    --image $IMAGE_URI `
    --region $REGION `
    --project $PROJECT_ID `
    --platform managed `
    --allow-unauthenticated `
    --memory 4Gi `
    --cpu 2 `
    --concurrency 80 `
    --min-instances 0 `
    --max-instances 10 `
    --timeout 300s `
    --service-account $SERVICE_ACCOUNT `
    --set-cloudsql-instances $CLOUD_SQL_INSTANCE `
    --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,ENVIRONMENT=production,GCS_BUCKET_NAME=$GCS_BUCKET,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,DB_USER=postgres,DB_NAME=gtip_db,WEB_CONCURRENCY=2,CORS_ALLOWED_ORIGINS=$WEB_ORIGIN" `
    --set-secrets "DB_PASS=gtip-db-password:latest,JWT_SECRET_KEY=gtip-jwt-secret:latest" `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Backend Cloud Run dağıtımı başarısız." }

& gcloud.cmd run services describe gtip-backend --region $REGION --project $PROJECT_ID --format="value(status.url)"
