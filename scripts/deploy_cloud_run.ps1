$PROJECT_ID = 'gtip-tespit-projesi'
$REGION = 'europe-west4'
$REPO_NAME = 'gtip-repo'
$IMAGE_URI = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/backend:latest"
$WEB_IMAGE_URI = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/web:latest"
$CLOUD_SQL_INSTANCE = 'gtip-tespit-projesi:europe-west4:gtip-db-west4'
$GCS_BUCKET = 'gtip-storage-west4'
$SERVICE_ACCOUNT = 'gtip-ai-sa@gtip-tespit-projesi.iam.gserviceaccount.com'

Write-Host "=========================================================="
Write-Host "  1. CLOUD BUILD: BACKEND DOCKER İMAJI DERLENİYOR ($REGION)..."
Write-Host "=========================================================="
gcloud.cmd builds submit --tag $IMAGE_URI .
if ($LASTEXITCODE -ne 0) { Write-Error "Backend build hatası!"; exit 1 }

Write-Host "=========================================================="
Write-Host "  2. CLOUD BUILD: FRONTEND (WEB) DOCKER İMAJI DERLENİYOR ($REGION)..."
Write-Host "=========================================================="
gcloud.cmd builds submit --tag $WEB_IMAGE_URI ./web
if ($LASTEXITCODE -ne 0) { Write-Error "Web build hatası!"; exit 1 }

Write-Host "=========================================================="
Write-Host "  3. CLOUD RUN: BACKEND SERVİSİ YAYINLANIRKEN ($REGION)..."
Write-Host "=========================================================="
gcloud.cmd run deploy gtip-backend `
    --image $IMAGE_URI `
    --region $REGION `
    --platform managed `
    --allow-unauthenticated `
    --memory 4Gi `
    --cpu 2 `
    --concurrency 80 `
    --min-instances 0 `
    --max-instances 10 `
    --timeout 300s `
    --add-cloudsql-instances $CLOUD_SQL_INSTANCE `
    --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,ENVIRONMENT=production,GCS_BUCKET_NAME=$GCS_BUCKET,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,WEB_CONCURRENCY=2,CORS_ALLOWED_ORIGINS=https://gtip-web-230333256951.europe-west4.run.app,https://gtip-web-230333256951.europe-west3.run.app" `
    --set-secrets "GEMINI_API_KEY=gtip-gemini-api-key:latest,JWT_SECRET_KEY=gtip-jwt-secret:latest,DB_PASS=gtip-db-password:latest"

if ($LASTEXITCODE -ne 0) { Write-Error "Backend deploy hatası!"; exit 1 }
$BACKEND_URL = "https://gtip-backend-230333256951.$REGION.run.app"

Write-Host "=========================================================="
Write-Host "  4. CLOUD RUN: WEB FRONTEND SERVİSİ YAYINLANIRKEN ($REGION)..."
Write-Host "=========================================================="
gcloud.cmd run deploy gtip-web `
    --image $WEB_IMAGE_URI `
    --region $REGION `
    --platform managed `
    --allow-unauthenticated `
    --memory 512Mi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 10 `
    --set-env-vars "VITE_API_URL=${BACKEND_URL}/api/v1"

if ($LASTEXITCODE -ne 0) { Write-Error "Web deploy hatası!"; exit 1 }
Write-Host "=========================================================="
Write-Host "  TÜM SİSTEM BAŞARIYLA BULUTA YÜKLENDİ VE CANLIDIR!"
Write-Host "  Backend URL: $BACKEND_URL"
Write-Host "  Web Sitesi : https://gtip-web-230333256951.$REGION.run.app"
Write-Host "=========================================================="
