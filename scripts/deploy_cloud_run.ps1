$PROJECT_ID = 'gumruk-mevzuat'
$REGION = 'us-central1'
$REPO_NAME = 'gtip-repo'
$IMAGE_URI = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/backend:latest"
$WEB_IMAGE_URI = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/web:latest"
$CLOUD_SQL_INSTANCE = 'gumruk-mevzuat:us-central1:gumruk-db'
$GCS_BUCKET = 'gumruk-mevzuat-storage-us-central1'
$SERVICE_ACCOUNT = "gtip-backend-sa@$PROJECT_ID.iam.gserviceaccount.com"

Write-Host "=========================================================="
Write-Host "  GCP US-CENTRAL1 DEPLOYMENT ($PROJECT_ID)"
Write-Host "=========================================================="
gcloud.cmd config set project $PROJECT_ID
gcloud.cmd config set compute/region $REGION

# 0. Service Account kontrolü ve IAM
Write-Host "  0. SERVICE ACCOUNT KONTROL EDİLİYOR..."
gcloud.cmd iam service-accounts describe $SERVICE_ACCOUNT 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Service Account oluşturuluyor: gtip-backend-sa..."
    gcloud.cmd iam service-accounts create gtip-backend-sa --display-name="GTIP Backend Service Account" 2>$null
    gcloud.cmd projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/aiplatform.user" 2>$null
    gcloud.cmd projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/storage.admin" 2>$null
    gcloud.cmd projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/cloudsql.client" 2>$null
    gcloud.cmd projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/secretmanager.secretAccessor" 2>$null
}

Write-Host "=========================================================="
Write-Host "  0a. GCS BUCKET OLUŞTURULUYOR ($GCS_BUCKET)..."
Write-Host "=========================================================="
gcloud.cmd storage buckets describe "gs://$GCS_BUCKET" 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud.cmd storage buckets create "gs://$GCS_BUCKET" --location=$REGION --uniform-bucket-level-access
    Write-Host "  Bucket oluşturuldu: gs://$GCS_BUCKET"
} else {
    Write-Host "  Bucket zaten mevcut: gs://$GCS_BUCKET"
}

Write-Host "=========================================================="
Write-Host "  0b. CLOUD SQL API VE INSTANCE KONTROL EDİLİYOR..."
Write-Host "=========================================================="
gcloud.cmd services enable sqladmin.googleapis.com --project $PROJECT_ID 2>$null
$SQL_INSTANCE_NAME = "gumruk-db"
gcloud.cmd sql instances describe $SQL_INSTANCE_NAME --project $PROJECT_ID 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Cloud SQL instance oluşturuluyor: $SQL_INSTANCE_NAME (Bu 5-10 dakika sürebilir)..."
    gcloud.cmd sql instances create $SQL_INSTANCE_NAME `
        --project $PROJECT_ID `
        --region $REGION `
        --database-version POSTGRES_15 `
        --tier db-f1-micro `
        --storage-type SSD `
        --storage-size 10GB `
        --no-backup
    if ($LASTEXITCODE -ne 0) { Write-Error "Cloud SQL instance oluşturma hatası!"; exit 1 }

    # Veritabanı ve kullanıcı oluştur
    gcloud.cmd sql databases create gtip_db --instance $SQL_INSTANCE_NAME --project $PROJECT_ID 2>$null
    Write-Host "  Cloud SQL instance hazır: ${PROJECT_ID}:${REGION}:${SQL_INSTANCE_NAME}"
} else {
    Write-Host "  Cloud SQL instance zaten mevcut: $SQL_INSTANCE_NAME"
}

Write-Host "=========================================================="
Write-Host "  1. CLOUD BUILD: BACKEND DOCKER İMAJI DERLENİYOR ($REGION)..."
Write-Host "=========================================================="
gcloud.cmd builds submit --tag $IMAGE_URI .
if ($LASTEXITCODE -ne 0) { Write-Error "Backend build hatası!"; exit 1 }

Write-Host "=========================================================="
Write-Host "  2. CLOUD RUN: BACKEND SERVİSİ YAYINLANIRKEN ($REGION)..."
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
    --service-account $SERVICE_ACCOUNT `
    --add-cloudsql-instances $CLOUD_SQL_INSTANCE `
    --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,ENVIRONMENT=production,PRIMARY_AI_MODEL=gemini-2.5-flash,EXTRACTOR_LLM_MODEL=gemini-2.5-flash-lite,REASONING_LLM_MODEL=gemini-2.5-flash,AUDITOR_LLM_MODEL=gemini-2.5-flash,EMBEDDING_MODEL=text-embedding-005,GCS_BUCKET_NAME=$GCS_BUCKET,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,WEB_CONCURRENCY=2,CORS_ALLOWED_ORIGINS=*" `
    --set-secrets "DB_PASS=gtip-db-password:latest"

if ($LASTEXITCODE -ne 0) { Write-Error "Backend deploy hatası!"; exit 1 }

$BACKEND_RAW_URL = gcloud.cmd run services describe gtip-backend --region $REGION --format="value(status.url)"
$BACKEND_URL = $BACKEND_RAW_URL.Trim()
Write-Host "  Backend URL Hazır: $BACKEND_URL"

Write-Host "=========================================================="
Write-Host "  3. CLOUD BUILD: FRONTEND (WEB) DOCKER İMAJI DERLENİYOR ($REGION)..."
Write-Host "=========================================================="
gcloud.cmd builds submit --tag $WEB_IMAGE_URI ./web
if ($LASTEXITCODE -ne 0) { Write-Error "Web build hatası!"; exit 1 }

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
    --max-instances 10

if ($LASTEXITCODE -ne 0) { Write-Error "Web deploy hatası!"; exit 1 }

$WEB_RAW_URL = gcloud.cmd run services describe gtip-web --region $REGION --format="value(status.url)"
$WEB_URL = $WEB_RAW_URL.Trim()

# Backend CORS güncellemesi
gcloud.cmd run services update gtip-backend --region $REGION --update-env-vars "CORS_ALLOWED_ORIGINS=$WEB_URL" 2>$null

Write-Host "=========================================================="
Write-Host "  TÜM SİSTEM BAŞARIYLA US-CENTRAL1 BÖLGESİNE YÜKLENDİ!"
Write-Host "  Backend URL: $BACKEND_URL"
Write-Host "  Web Sitesi : $WEB_URL"
Write-Host "=========================================================="
