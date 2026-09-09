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

$JobName = "gtip-seed-tgtc-2026"
$CloudSqlConnection = "$ProjectId`:$Region`:gumruk-db"
$ServiceAccount = "gtip-backend-sa@$ProjectId.iam.gserviceaccount.com"
$envVars = "GCP_PROJECT_ID=$ProjectId,GCP_REGION=$Region,VERTEX_AI_LOCATION=$Region,ENVIRONMENT=production,CLOUD_RUN_JOB=$JobName,CLOUD_SQL_CONNECTION_NAME=$CloudSqlConnection,INSTANCE_CONNECTION_NAME=$CloudSqlConnection,DB_USER=postgres,DB_NAME=gtip_db,DB_POOL_SIZE=1,DB_MAX_OVERFLOW=1,USE_GCP_EMULATOR=false,SKIP_TGTC_AUTO_SEED=true,EMBEDDING_MODEL=text-embedding-005"

function Assert-LastExitCode([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

function Invoke-GcloudCheck([string]$CommandLine) {
    & cmd.exe /c "gcloud.cmd $CommandLine >nul 2>&1"
}

if (-not (Get-Command gcloud.cmd -ErrorAction SilentlyContinue)) { throw "gcloud.cmd bulunamadı." }
Invoke-GcloudCheck "artifacts docker images describe $Image --project $ProjectId"
Assert-LastExitCode "Immutable backend image bulunamadı: $Image"
Invoke-GcloudCheck "sql instances describe gumruk-db --project $ProjectId"
Assert-LastExitCode "Cloud SQL gumruk-db bulunamadı."
Invoke-GcloudCheck "secrets versions describe latest --secret gtip-db-password --project $ProjectId"
Assert-LastExitCode "gtip-db-password latest sürümü bulunamadı."

Invoke-GcloudCheck "run jobs describe $JobName --region $Region --project $ProjectId"
$action = if ($LASTEXITCODE -eq 0) { "update" } else { "create" }

& gcloud.cmd run jobs $action $JobName `
    --image $Image `
    --region $Region `
    --project $ProjectId `
    --tasks 1 `
    --parallelism 1 `
    --max-retries 0 `
    --task-timeout 7200s `
    --memory 4Gi `
    --cpu 2 `
    --service-account $ServiceAccount `
    --set-cloudsql-instances $CloudSqlConnection `
    --set-env-vars $envVars `
    --set-secrets "DB_PASS=gtip-db-password:latest" `
    --command python `
    "--args=-m,scripts.seed_tgtc_2026" `
    --labels "app=gtip,component=seed,release=$Release" `
    --quiet
Assert-LastExitCode "TGTC seed job dağıtılamadı."

& gcloud.cmd run jobs add-iam-policy-binding $JobName `
    --region $Region `
    --project $ProjectId `
    --member "serviceAccount:$ServiceAccount" `
    --role "roles/run.invoker" `
    --quiet
Assert-LastExitCode "TGTC seed job invoker yetkisi verilemedi."

Write-Host "Hazır: $JobName ($Image)"
Write-Host "Bu job otomatik çalıştırılmaz. Restore verisi eksikse kontrollü olarak execute edin."
