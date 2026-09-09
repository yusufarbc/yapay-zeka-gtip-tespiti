[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^projects/[^/]+/backups/[^/]+$')]
    [string]$BackupName,
    [string]$ProjectId = "gumruk-mevzuat",
    [string]$Region = "us-central1",
    [string]$InstanceName = "gumruk-db",
    [int]$Cpu = 2,
    [int]$MemoryMiB = 7680
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-LastExitCode([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

if (-not (Get-Command gcloud.cmd -ErrorAction SilentlyContinue)) { throw "gcloud.cmd bulunamadı." }
if ($Cpu -lt 2 -or $MemoryMiB -lt 3840) {
    throw "Üretim restore profili en az 2 vCPU ve 3840 MiB bellek gerektirir."
}

& gcloud.cmd sql instances describe $InstanceName --project $ProjectId *> $null
if ($LASTEXITCODE -eq 0) {
    throw "Hedef instance zaten var: $InstanceName. Bu betik mevcut instance üzerine restore yapmaz."
}

$backupRaw = & gcloud.cmd sql backups describe $BackupName --project $ProjectId --format=json
Assert-LastExitCode "FINAL backup bulunamadı veya erişilemiyor: $BackupName"
$backup = $backupRaw | ConvertFrom-Json
if ($backup.expireTime -and ([DateTimeOffset]$backup.expireTime -le [DateTimeOffset]::UtcNow)) {
    throw "FINAL backup süresi dolmuş: $($backup.expireTime)"
}

foreach ($scheduler in @("resmi-gazete-daily-sync", "official-btb-daily-sync")) {
    & gcloud.cmd scheduler jobs describe $scheduler --location $Region --project $ProjectId *> $null
    if ($LASTEXITCODE -eq 0) {
        & gcloud.cmd scheduler jobs pause $scheduler --location $Region --project $ProjectId --quiet
        Assert-LastExitCode "Restore öncesi scheduler durdurulamadı: $scheduler"
    }
}

$target = "$ProjectId/$Region/$InstanceName"
if (-not $PSCmdlet.ShouldProcess($target, "FINAL backup'tan yeni regional HA Cloud SQL instance restore et")) {
    return
}

& gcloud.cmd sql backups restore $BackupName `
    --restore-instance=$InstanceName `
    --project=$ProjectId `
    --region=$Region `
    --database-version=POSTGRES_15 `
    --cpu=$Cpu `
    --memory="$($MemoryMiB)MiB" `
    --availability-type=regional `
    --backup `
    --backup-start-time=00:00 `
    --enable-point-in-time-recovery `
    --retained-backups-count=14 `
    --retained-transaction-log-days=7 `
    --storage-auto-increase `
    --deletion-protection `
    --final-backup `
    --final-backup-retention-days=30 `
    --timeout=3600 `
    --quiet
Assert-LastExitCode "Cloud SQL restore başarısız."

$instanceRaw = & gcloud.cmd sql instances describe $InstanceName --project $ProjectId --format=json
Assert-LastExitCode "Restore sonrası instance okunamadı."
$instance = $instanceRaw | ConvertFrom-Json
if ($instance.state -ne "RUNNABLE") { throw "Restore tamamlandı ancak instance hazır değil: $($instance.state)" }
if ($instance.region -ne $Region -or $instance.settings.availabilityType -ne "REGIONAL") {
    throw "Restore edilen instance üretim HA/bölge profilinde değil."
}
& gcloud.cmd sql databases describe gtip_db --instance $InstanceName --project $ProjectId *> $null
Assert-LastExitCode "Restore tamamlandı fakat gtip_db bulunamadı."

Write-Host "Cloud SQL FINAL backup restore tamamlandı: $target"
Write-Host "Şimdi mevcut gtip-db-password secret'ı ile gerçek bağlantıyı test edin; doğrulamadan seed çalıştırmayın."
