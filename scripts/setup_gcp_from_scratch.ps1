$ErrorActionPreference = "Stop"

Write-Warning "Eski europe-west/gtip-tespit-projesi kurulum betiği kaldırıldı; açık metin parola kullanılmaz."
Write-Host "Canonical hedef: gumruk-mevzuat / us-central1"
Write-Host "Dağıtım scripts/deploy_cloud_run.ps1 ile devam ediyor."

& (Join-Path $PSScriptRoot "deploy_cloud_run.ps1")
