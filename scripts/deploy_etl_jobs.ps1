$ErrorActionPreference = "Stop"

$PROJECT_ID = "gumruk-mevzuat"
$REGION = "us-central1"
$REPO_NAME = "gtip-repo"
$IMAGE_URI = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/backend:latest"
$CLOUD_SQL_INSTANCE = "$PROJECT_ID`:$REGION`:gumruk-db"
$GCS_BUCKET = "gumruk-mevzuat-storage-us-central1"
$SERVICE_ACCOUNT = "gtip-backend-sa@$PROJECT_ID.iam.gserviceaccount.com"
$ARCHIVE_JOB = "gtip-archive-backfill"
$DAILY_JOB = "gtip-daily-sync"
$BTB_JOB = "gtip-official-btb-sync"
$SCHEDULER_JOB = "resmi-gazete-daily-sync"
$BTB_SCHEDULER_JOB = "official-btb-daily-sync"
$ENV_VARS = "GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,ENVIRONMENT=production,GCS_BUCKET_NAME=$GCS_BUCKET,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_INSTANCE,DB_USER=postgres,DB_NAME=gtip_db,USE_GCP_EMULATOR=false,CORS_ALLOWED_ORIGINS=https://gtip-web-gu6pxpqefa-uc.a.run.app,EXTRACTOR_LLM_MODEL=gemini-2.5-flash-lite,EMBEDDING_MODEL=text-embedding-005"

function Assert-LastExitCode([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

function Deploy-EtlJob([string]$Name, [string]$ContainerArgs, [string]$Timeout, [string]$Memory, [string]$Cpu) {
    $existingJob = & gcloud.cmd run jobs list --region $REGION --project $PROJECT_ID --filter="metadata.name=$Name" --format="value(metadata.name)"
    Assert-LastExitCode "Cloud Run Job listesi okunamadı."
    $action = if (($existingJob | Out-String).Trim()) { "update" } else { "create" }

    & gcloud.cmd run jobs $action $Name `
        --image $IMAGE_URI `
        --region $REGION `
        --project $PROJECT_ID `
        --tasks 1 `
        --max-retries 3 `
        --task-timeout $Timeout `
        --memory $Memory `
        --cpu $Cpu `
        --service-account $SERVICE_ACCOUNT `
        --set-cloudsql-instances $CLOUD_SQL_INSTANCE `
        --set-env-vars $ENV_VARS `
        --set-secrets "DB_PASS=gtip-db-password:latest" `
        --command python `
        "--args=$ContainerArgs" `
        --quiet
    Assert-LastExitCode "Cloud Run Job dağıtımı başarısız: $Name"
}

Write-Host "GCP API'leri ve secret doğrulanıyor..."
& gcloud.cmd services enable run.googleapis.com cloudscheduler.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com --project $PROJECT_ID --quiet
Assert-LastExitCode "Gerekli GCP API'leri etkinleştirilemedi."
& gcloud.cmd secrets describe gtip-db-password --project $PROJECT_ID *> $null
Assert-LastExitCode "gtip-db-password Secret Manager'da bulunamadı."

Write-Host "6 yıllık arşiv ve günlük ETL işleri dağıtılıyor..."
Deploy-EtlJob $ARCHIVE_JOB "scripts/spider_resmi_gazete_archive.py,--mode,archive" "86400s" "4Gi" "2"
Deploy-EtlJob $DAILY_JOB "scripts/spider_resmi_gazete_archive.py,--mode,daily,--days-back,3" "3600s" "2Gi" "1"
Deploy-EtlJob $BTB_JOB "-m,scripts.scrape_official_btb" "21600s" "2Gi" "1"

Write-Host "Servis hesabına yalnızca ETL Job çağırma yetkisi veriliyor..."
foreach ($jobName in @($ARCHIVE_JOB, $DAILY_JOB, $BTB_JOB)) {
    & gcloud.cmd run jobs add-iam-policy-binding $jobName `
        --region $REGION `
        --project $PROJECT_ID `
        --member "serviceAccount:$SERVICE_ACCOUNT" `
        --role "roles/run.invoker" `
        --quiet
    Assert-LastExitCode "Cloud Run Job invoker yetkisi verilemedi: $jobName"
}

$JOB_URI = "https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/$DAILY_JOB`:run"
$existingScheduler = & gcloud.cmd scheduler jobs list --location $REGION --project $PROJECT_ID --filter="name:$SCHEDULER_JOB" --format="value(name)"
Assert-LastExitCode "Cloud Scheduler listesi okunamadı."
$schedulerAction = if (($existingScheduler | Out-String).Trim()) { "update" } else { "create" }
$headerFlag = if ($schedulerAction -eq "update") {
    "--update-headers=Content-Type=application/json"
} else {
    "--headers=Content-Type=application/json"
}

& gcloud.cmd scheduler jobs $schedulerAction http $SCHEDULER_JOB `
    --location $REGION `
    --project $PROJECT_ID `
    --schedule "0 2 * * *" `
    --time-zone "Europe/Istanbul" `
    --uri $JOB_URI `
    --http-method POST `
    --oauth-service-account-email $SERVICE_ACCOUNT `
    --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
    $headerFlag `
    --message-body "{}" `
    --quiet
Assert-LastExitCode "Cloud Scheduler yapılandırılamadı."

Write-Host "ETL hazır: $ARCHIVE_JOB, $DAILY_JOB; her gece 02:00 Europe/Istanbul."

$BTB_JOB_URI = "https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/$BTB_JOB`:run"
$existingBtbScheduler = & gcloud.cmd scheduler jobs list --location $REGION --project $PROJECT_ID --filter="name:$BTB_SCHEDULER_JOB" --format="value(name)"
Assert-LastExitCode "BTB Scheduler listesi okunamadı."
$btbSchedulerAction = if (($existingBtbScheduler | Out-String).Trim()) { "update" } else { "create" }
$btbHeaderFlag = if ($btbSchedulerAction -eq "update") {
    "--update-headers=Content-Type=application/json"
} else {
    "--headers=Content-Type=application/json"
}

& gcloud.cmd scheduler jobs $btbSchedulerAction http $BTB_SCHEDULER_JOB `
    --location $REGION `
    --project $PROJECT_ID `
    --schedule "0 3 * * *" `
    --time-zone "Europe/Istanbul" `
    --uri $BTB_JOB_URI `
    --http-method POST `
    --oauth-service-account-email $SERVICE_ACCOUNT `
    --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
    $btbHeaderFlag `
    --message-body "{}" `
    --quiet
Assert-LastExitCode "Resmî BTB Scheduler yapılandırılamadı."

Write-Host "Resmî BTB işi hazır: $BTB_JOB; her gece 03:00 Europe/Istanbul."
