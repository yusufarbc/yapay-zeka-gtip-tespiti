[CmdletBinding()]
param(
    [string]$ProjectId = "gumruk-mevzuat",
    [string]$Region = "us-central1",
    [switch]$RequireSchedulersEnabled
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$failures = [System.Collections.Generic.List[string]]::new()

function Add-Failure([string]$Message) {
    $script:failures.Add($Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Get-GcloudJson([string[]]$Arguments, [string]$FailureMessage) {
    $raw = & gcloud.cmd @Arguments --format=json
    if ($LASTEXITCODE -ne 0) {
        Add-Failure $FailureMessage
        return $null
    }
    return ($raw | ConvertFrom-Json)
}

function Assert-Http([string]$Url, [string]$Name) {
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 30 -UseBasicParsing
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
            Add-Failure "$Name HTTP $($response.StatusCode): $Url"
        } else {
            Write-Host "[OK] $Name"
        }
    } catch {
        Add-Failure "$Name erişilemiyor: $Url ($($_.Exception.Message))"
    }
}

if (-not (Get-Command gcloud.cmd -ErrorAction SilentlyContinue)) { throw "gcloud.cmd bulunamadı." }

$sql = Get-GcloudJson @("sql", "instances", "describe", "gumruk-db", "--project", $ProjectId) "Cloud SQL gumruk-db yok."
if ($sql) {
    if ($sql.state -ne "RUNNABLE") { Add-Failure "Cloud SQL state=$($sql.state)" }
    if ($sql.region -ne $Region) { Add-Failure "Cloud SQL yanlış bölgede: $($sql.region)" }
    if (-not $sql.settings.deletionProtectionEnabled) { Add-Failure "Cloud SQL deletion protection kapalı." }
    if (-not $sql.settings.storageAutoResize) { Add-Failure "Cloud SQL storage auto-growth kapalı." }
    if (-not $sql.settings.backupConfiguration.enabled) { Add-Failure "Cloud SQL backup kapalı." }
    if (-not $sql.settings.backupConfiguration.pointInTimeRecoveryEnabled) { Add-Failure "Cloud SQL PITR kapalı." }
}

$backend = Get-GcloudJson @("run", "services", "describe", "gtip-backend", "--region", $Region, "--project", $ProjectId) "Backend servisi yok."
$web = Get-GcloudJson @("run", "services", "describe", "gtip-web", "--region", $Region, "--project", $ProjectId) "Web servisi yok."
if ($backend) {
    $backendUrl = [string]$backend.status.url
    Assert-Http "$backendUrl/api/v1/health" "Backend health"
    Assert-Http "$backendUrl/api/v1/ready" "Backend readiness"
    $backendImage = [string]$backend.spec.template.spec.containers[0].image
    if ($backendImage -notmatch '@sha256:[0-9a-f]{64}$') { Add-Failure "Backend immutable digest kullanmıyor: $backendImage" }
}
if ($web) {
    $webUrl = [string]$web.status.url
    Assert-Http "$webUrl" "Web UI"
    Assert-Http "$webUrl/api/v1/health" "Web -> backend proxy"
    $webImage = [string]$web.spec.template.spec.containers[0].image
    if ($webImage -notmatch '@sha256:[0-9a-f]{64}$') { Add-Failure "Web immutable digest kullanmıyor: $webImage" }
}

$jobNames = @("gtip-archive-backfill", "gtip-daily-sync", "gtip-official-btb-sync", "gtip-seed-tgtc-2026")
$jobImages = @()
foreach ($jobName in $jobNames) {
    $job = Get-GcloudJson @("run", "jobs", "describe", $jobName, "--region", $Region, "--project", $ProjectId) "Cloud Run Job yok: $jobName"
    if ($job) {
        $image = [string]$job.spec.template.spec.template.spec.containers[0].image
        if (-not $image) { $image = [string]$job.template.template.containers[0].image }
        $jobImages += $image
        if ($image -notmatch '@sha256:[0-9a-f]{64}$') { Add-Failure "$jobName immutable digest kullanmıyor: $image" }
    }
}
if (@($jobImages | Where-Object { $_ } | Select-Object -Unique).Count -gt 1) {
    Add-Failure "Cloud Run Job'lar aynı backend digest'ini kullanmıyor."
}

foreach ($schedulerName in @("resmi-gazete-daily-sync", "official-btb-daily-sync")) {
    $scheduler = Get-GcloudJson @("scheduler", "jobs", "describe", $schedulerName, "--location", $Region, "--project", $ProjectId) "Scheduler yok: $schedulerName"
    if ($scheduler) {
        $expectedState = if ($RequireSchedulersEnabled) { "ENABLED" } else { "PAUSED" }
        if ($scheduler.state -ne $expectedState) {
            Add-Failure "$schedulerName state=$($scheduler.state), beklenen=$expectedState"
        }
    }
}

$bucket = Get-GcloudJson @("storage", "buckets", "describe", "gs://$ProjectId-storage-$Region", "--project", $ProjectId) "GCS bucket yok."
if ($bucket) {
    $pap = ""
    if ($bucket.PSObject.Properties.Match('public_access_prevention').Count -gt 0) {
        $pap = [string]$bucket.public_access_prevention
    } elseif ($bucket.PSObject.Properties.Match('iamConfiguration').Count -gt 0 -and $bucket.iamConfiguration.PSObject.Properties.Match('publicAccessPrevention').Count -gt 0) {
        $pap = [string]$bucket.iamConfiguration.publicAccessPrevention
    }
    if ($pap -ne "enforced") {
        Add-Failure "GCS public access prevention enforced değil ($pap)."
    }
    $cors = @()
    if ($bucket.PSObject.Properties.Match('cors_config').Count -gt 0) { $cors += @($bucket.cors_config) }
    if ($bucket.PSObject.Properties.Match('cors').Count -gt 0) { $cors += @($bucket.cors) }
    if (@($cors | Where-Object { $_ }).Count -eq 0) { Add-Failure "GCS CORS yapılandırması yok." }
}

if ($failures.Count -gt 0) {
    throw "Deployment doğrulaması $($failures.Count) hata ile başarısız."
}
Write-Host "Tüm otomatik deployment kontrolleri başarılı."
