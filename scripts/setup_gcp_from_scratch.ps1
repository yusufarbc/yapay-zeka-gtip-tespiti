# ==============================================================================
# GTİP Tespit - GCP Sıfırdan Tam Kurulum ve Canlıya Alma Orkestrasyon Betiği
# Bölge: europe-west4 (Hollanda / Eemshaven)
# ==============================================================================
$ErrorActionPreference = "Stop"

$PROJECT_ID = "gtip-tespit-projesi"
$REGION = "europe-west4"
$ZONE = "europe-west4-a"
$REPO_NAME = "gtip-repo"
$GCS_BUCKET = "gtip-storage-west4"
$DB_INSTANCE_NAME = "gtip-sql-postgres-west4"
$DB_NAME = "gtip_db"
$DB_USER = "postgres"
$SERVICE_ACCOUNT_NAME = "gtip-backend-sa"
$SERVICE_ACCOUNT = "$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"
$CLOUD_SQL_CONNECTION = "$PROJECT_ID:$REGION:$DB_INSTANCE_NAME"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "🚀 GTİP TESPİT SİSTEMİ - GCP SIFIRDAN KURULUM VE DAĞITIM" -ForegroundColor Green
Write-Host "   Proje ID:    $PROJECT_ID"
Write-Host "   Bölge:       $REGION"
Write-Host "   Cloud SQL:   $DB_INSTANCE_NAME"
Write-Host "   GCS Kova:    $GCS_BUCKET"
Write-Host "=================================================================="

# 1. GCP Proje ve Temel API'lerin Etkinleştirilmesi
Write-Host "`n🔧 [1/8] GCP Servis API'leri Etkinleştiriliyor..." -ForegroundColor Yellow
gcloud config set project $PROJECT_ID
gcloud services enable `
    run.googleapis.com `
    sqladmin.googleapis.com `
    aiplatform.googleapis.com `
    storage.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com `
    secretmanager.googleapis.com `
    cloudscheduler.googleapis.com

# 2. Artifact Registry Docker Deposunun Oluşturulması
Write-Host "`n📦 [2/8] Artifact Registry Deposu ($REPO_NAME) Kontrol Ediliyor..." -ForegroundColor Yellow
gcloud artifacts repositories create $REPO_NAME `
    --repository-format=docker `
    --location=$REGION `
    --description="GTIP Tespit Docker Images" `
    2>$null
if ($LASTEXITCODE -eq 0) { Write-Host "   ✅ Artifact Registry deposu oluşturuldu." -ForegroundColor Green }
else { Write-Host "   ℹ️ Artifact Registry deposu zaten mevcut." -ForegroundColor Gray }

# 3. Cloud Storage Kovasının Oluşturulması & Public PDF Erişimi
Write-Host "`n🪣 [3/8] Cloud Storage Kovası ($GCS_BUCKET) Kontrol Ediliyor..." -ForegroundColor Yellow
gcloud storage buckets create gs://$GCS_BUCKET --location=$REGION --project=$PROJECT_ID 2>$null
if ($LASTEXITCODE -eq 0) { Write-Host "   ✅ Cloud Storage kovası oluşturuldu." -ForegroundColor Green }
else { Write-Host "   ℹ️ Cloud Storage kovası zaten mevcut." -ForegroundColor Gray }

# PDF'lerin doğrudan tarayıcıda açılabilmesi için public okuma izni
gcloud storage buckets add-iam-policy-binding gs://$GCS_BUCKET --member="allUsers" --role="roles/storage.objectViewer"

# 4. Service Account ve IAM Yetkilerinin Tanımlanması
Write-Host "`n🔑 [4/8] Service Account ($SERVICE_ACCOUNT_NAME) Yetkilendiriliyor..." -ForegroundColor Yellow
gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME `
    --display-name="GTIP Backend Service Account" `
    --project=$PROJECT_ID `
    2>$null

$ROLES = @(
    "roles/cloudsql.client",
    "roles/aiplatform.user",
    "roles/storage.objectAdmin",
    "roles/secretmanager.secretAccessor"
)

foreach ($ROLE in $ROLES) {
    gcloud projects add-iam-policy-binding $PROJECT_ID `
        --member="serviceAccount:$SERVICE_ACCOUNT" `
        --role="$ROLE" `
        --condition=None `
        --quiet
}
Write-Host "   ✅ Service Account yetkileri başarıyla tanımlandı." -ForegroundColor Green

# 5. Cloud SQL PostgreSQL 15 & pgvector Kurulumu
Write-Host "`n🗄️ [5/8] Cloud SQL PostgreSQL 15 ($DB_INSTANCE_NAME) Kontrol Ediliyor..." -ForegroundColor Yellow
gcloud sql instances describe $DB_INSTANCE_NAME --project=$PROJECT_ID 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "   ⏳ Cloud SQL instance oluşturuluyor (Bu işlem 3-5 dk sürebilir)..." -ForegroundColor Yellow
    gcloud sql instances create $DB_INSTANCE_NAME `
        --database-version=POSTGRES_15 `
        --tier=db-custom-2-7680 `
        --region=$REGION `
        --zone=$ZONE `
        --storage-type=SSD `
        --storage-size=20GB `
        --storage-auto-increase `
        --project=$PROJECT_ID

    # Veritabanı ve Kullanıcı Oluştur
    gcloud sql databases create $DB_NAME --instance=$DB_INSTANCE_NAME --project=$PROJECT_ID
    gcloud sql users set-password $DB_USER --instance=$DB_INSTANCE_NAME --password="GtipSecurePassword2026!" --project=$PROJECT_ID
    Write-Host "   ✅ Cloud SQL başarıyla oluşturuldu." -ForegroundColor Green
} else {
    Write-Host "   ℹ️ Cloud SQL instance zaten aktif." -ForegroundColor Gray
}

# 6. Secret Manager Secret Değerlerinin Doğrulanması
Write-Host "`n🔐 [6/8] Secret Manager Yapılandırması..." -ForegroundColor Yellow
$SECRETS = @("gtip-gemini-api-key", "gtip-jwt-secret", "gtip-db-password")
foreach ($SEC in $SECRETS) {
    gcloud secrets describe $SEC --project=$PROJECT_ID 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   ⚠️ $SEC secret'ı bulunamadı. Lütfen 'gcloud secrets create $SEC --data-file=...' ile ekleyin." -ForegroundColor Red
    }
}

# 7. Cloud Run Backend & Web Frontend Dağıtımı
Write-Host "`n🚀 [7/8] Cloud Run Backend ve Frontend Dağıtılıyor..." -ForegroundColor Yellow
powershell -ExecutionPolicy Bypass -File scripts/deploy_cloud_run.ps1

# 8. Cloud Run ETL Jobs & Cloud Scheduler Dağıtımı
Write-Host "`n⏱️ [8/8] Resmî Gazete ETL Cloud Run Jobs & Scheduler Dağıtılıyor..." -ForegroundColor Yellow
powershell -ExecutionPolicy Bypass -File scripts/deploy_etl_jobs.ps1

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host "🎉 GCP TÜM SİSTEM SIFIRDAN BAŞARIYLA KURULDU VE CANLIDA AKTİF!" -ForegroundColor Green
Write-Host "   Web UI:     https://gtip-web-230333256951.europe-west4.run.app"
Write-Host "   Backend:    https://gtip-backend-230333256951.europe-west4.run.app"
Write-Host "   Swagger:    https://gtip-backend-230333256951.europe-west4.run.app/docs"
Write-Host "=================================================================="
