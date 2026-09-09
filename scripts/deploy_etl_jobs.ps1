[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9.-]+-docker\.pkg\.dev/.+@sha256:[0-9a-f]{64}$')]
    [string]$Image,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9-]{0,49}$')]
    [string]$Release,
    [string]$ProjectId = "gumruk-mevzuat",
    [string]$Region = "us-central1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$CloudSqlConnection = "$ProjectId`:$Region`:gumruk-db"
$Bucket = "$ProjectId-storage-$Region"
$ServiceAccount = "gtip-backend-sa@$ProjectId.iam.gserviceaccount.com"
$SchedulerAccount = $ServiceAccount
$ArchiveJob = "gtip-archive-backfill"
$DailyJob = "gtip-daily-sync"
$BtbJob = "gtip-official-btb-sync"
$DailyScheduler = "resmi-gazete-daily-sync"
$BtbScheduler = "official-btb-daily-sync"

function Assert-LastExitCode([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

function Pause-SchedulerIfPresent([string]$Name) {
    & gcloud.cmd scheduler jobs describe $Name --location $Region --project $ProjectId *> $null
    if ($LASTEXITCODE -eq 0) {
        & gcloud.cmd scheduler jobs pause $Name --location $Region --project $ProjectId --quiet
        Assert-LastExitCode "Scheduler duraklatılamadı: $Name"
    }
}

function Deploy-EtlJob(
    [string]$Name,
    [string]$ContainerArgs,
    [string]$Timeout,
    [string]$Memory,
    [string]$Cpu,
    [string]$Retries
) {
    & gcloud.cmd run jobs describe $Name --region $Region --project $ProjectId *> $null
    $action = if ($LASTEXITCODE -eq 0) { "update" } else { "create" }
    $envVars = "GCP_PROJECT_ID=$ProjectId,GCP_REGION=$Region,VERTEX_AI_LOCATION=$Region,ENVIRONMENT=production,GCS_BUCKET_NAME=$Bucket,CLOUD_SQL_CONNECTION_NAME=$CloudSqlConnection,INSTANCE_CONNECTION_NAME=$CloudSqlConnection,DB_USER=postgres,DB_NAME=gtip_db,DB_POOL_SIZE=1,DB_MAX_OVERFLOW=1,USE_GCP_EMULATOR=false,SKIP_TGTC_AUTO_SEED=true,EXTRACTOR_LLM_MODEL=gemini-2.5-flash-lite,EMBEDDING_MODEL=text-embedding-005"

    & gcloud.cmd run jobs $action $Name `
        --image $Image `
        --region $Region `
        --project $ProjectId `
        --tasks 1 `
        --parallelism 1 `
        --max-retries $Retries `
        --task-timeout $Timeout `
        --memory $Memory `
        --cpu $Cpu `
        --service-account $ServiceAccount `
        --set-cloudsql-instances $CloudSqlConnection `
        --set-env-vars $envVars `
        --set-secrets "DB_PASS=gtip-db-password:latest" `
        --command python `
        "--args=$ContainerArgs" `
        --labels "app=gtip,component=etl,release=$Release" `
        --quiet
    Assert-LastExitCode "Cloud Run Job dağıtımı başarısız: $Name"

    & gcloud.cmd run jobs add-iam-policy-binding $Name `
        --region $Region `
        --project $ProjectId `
        --member "serviceAccount:$SchedulerAccount" `
        --role "roles/run.invoker" `
        --quiet *> $null
    Assert-LastExitCode "Job invoker yetkisi verilemedi: $Name"
}

function Upsert-Scheduler([string]$Name, [string]$TargetJob, [string]$Schedule, [string]$Description) {
    $uri = "https://run.googleapis.com/v2/projects/$ProjectId/locations/$Region/jobs/$TargetJob`:run"
    & gcloud.cmd scheduler jobs describe $Name --location $Region --project $ProjectId *> $null
    $action = if ($LASTEXITCODE -eq 0) { "update" } else { "create" }
    $headerFlag = if ($action -eq "update") {
        "--update-headers=Content-Type=application/json"
    } else {
        "--headers=Content-Type=application/json"
    }

    & gcloud.cmd scheduler jobs $action http $Name `
        --location $Region `
        --project $ProjectId `
        --schedule $Schedule `
        --time-zone "Europe/Istanbul" `
        --uri $uri `
        --http-method POST `
        --oauth-service-account-email $SchedulerAccount `
        --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
        $headerFlag `
        --message-body "{}" `
        --attempt-deadline 30s `
        --max-retry-attempts 2 `
        --min-backoff 30s `
        --max-backoff 300s `
        --max-doublings 3 `
        --description $Description `
        --quiet
    Assert-LastExitCode "Scheduler yapılandırılamadı: $Name"

    # Yeni oluşturulan scheduler varsayılan olarak etkin olabilir. Go-live doğrulaması
    # tamamlanana kadar her durumda PAUSED bırakılır.
    & gcloud.cmd scheduler jobs pause $Name --location $Region --project $ProjectId --quiet
    Assert-LastExitCode "Scheduler güvenli biçimde duraklatılamadı: $Name"
}

if (-not (Get-Command gcloud.cmd -ErrorAction SilentlyContinue)) { throw "gcloud.cmd bulunamadı." }
& gcloud.cmd artifacts docker images describe $Image --project $ProjectId *> $null
Assert-LastExitCode "Immutable backend image bulunamadı: $Image"
& gcloud.cmd sql instances describe gumruk-db --project $ProjectId *> $null
Assert-LastExitCode "Cloud SQL gumruk-db bulunamadı."
& gcloud.cmd secrets versions describe latest --secret gtip-db-password --project $ProjectId *> $null
Assert-LastExitCode "gtip-db-password latest sürümü bulunamadı."

Pause-SchedulerIfPresent $DailyScheduler
Pause-SchedulerIfPresent $BtbScheduler

Deploy-EtlJob $ArchiveJob "-m,scripts.spider_resmi_gazete_archive,--mode,archive" "86400s" "4Gi" "2" "2"
Deploy-EtlJob $DailyJob "-m,scripts.spider_resmi_gazete_archive,--mode,daily,--days-back,3" "3600s" "2Gi" "1" "2"
Deploy-EtlJob $BtbJob "-m,scripts.scrape_official_btb" "21600s" "2Gi" "1" "2"

Upsert-Scheduler $DailyScheduler $DailyJob "0 2 * * *" "Günlük Resmi Gazete GTIP senkronu"
Upsert-Scheduler $BtbScheduler $BtbJob "0 3 * * *" "Günlük resmi BTB senkronu"

Write-Host "Üç ETL job aynı immutable digest ile hazırlandı: $Image"
Write-Host "İki scheduler PAUSED bırakıldı. Daily ve BTB manuel execution doğrulandıktan sonra resume edin."
