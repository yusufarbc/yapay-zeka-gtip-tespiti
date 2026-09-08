#!/usr/bin/env bash
set -euo pipefail

echo "Bu eski kurulum betiği güvenlik nedeniyle devre dışıdır (yanlış proje/bölge ve açık metin parola içeriyordu)." >&2
echo "Canonical dağıtım: PowerShell ile scripts/deploy_cloud_run.ps1 ve scripts/deploy_etl_jobs.ps1" >&2
exit 2
