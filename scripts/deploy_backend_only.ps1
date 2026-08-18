$PROJECT_ID = 'gtip-tespit-projesi'
$REGION = 'europe-west3'
$REPO_NAME = 'gtip-repo'
$IMAGE_URI = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/backend:latest"
$CLOUD_SQL_INSTANCE = 'gtip-tespit-projesi:europe-west3:gtip-db'
$GCS_BUCKET = 'gtip-evrak-bucket-gtip-tespit-projesi'

Write-Host "1. Building backend image with Cloud Build..."
gcloud builds submit --tag $IMAGE_URI .

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed!"
    exit 1
}

Write-Host "2. Deploying backend to Cloud Run..."
gcloud run deploy gtip-backend `
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
    --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,ENVIRONMENT=production,GCS_BUCKET_NAME=$GCS_BUCKET,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,WEB_CONCURRENCY=2,CORS_ALLOWED_ORIGINS=https://gtip-web-230333256951.europe-west3.run.app" `
    --set-secrets "GEMINI_API_KEY=gtip-gemini-api-key:latest,JWT_SECRET_KEY=gtip-jwt-secret:latest,DB_PASS=gtip-db-password:latest"
