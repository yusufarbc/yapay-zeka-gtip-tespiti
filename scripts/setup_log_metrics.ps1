[CmdletBinding()]
param(
    [string]$ProjectId = "gumruk-mevzuat",
    [string]$ServiceName = "gtip-backend"
)

# ==============================================================================
# Cloud Logging log-based metric'leri.
#
# Uygulama logları önceden düz metin gidiyordu; Cloud Logging severity alanını
# dolduramıyor, hata ile bilgi satırı aynı seviyede görünüyordu. api/logging_config.py
# JSON'a çevirdikten sonra bu metrikler jsonPayload alanlarından doğrudan türetilebilir
# ve metin ayrıştırmaya ihtiyaç kalmaz.
#
# ÖNKOŞUL: Yapılandırılmış loglamayı içeren sürüm deploy edilmiş olmalı; aksi halde
# filtreler hiçbir satırla eşleşmez ve metrikler sürekli 0 döner.
#
# Alarm eşikleri burada tanımlanmaz: metrikler birkaç gün veri topladıktan sonra
# gerçek dağılıma bakılarak belirlenmelidir.
# ==============================================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-LastExitCode([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

$base = "resource.type=`"cloud_run_revision`" AND resource.labels.service_name=`"$ServiceName`""

$metrics = @(
    @{
        Name        = "gtip_analysis_errors"
        Description = "GTIP backend uygulama hatalari (severity=ERROR ve uzeri)"
        Filter      = "$base AND severity>=ERROR"
    },
    @{
        Name        = "gtip_manual_review"
        Description = "Manuel incelemeye dusen siniflandirma kararlari"
        Filter      = "$base AND jsonPayload.decision_status=`"MANUAL_REVIEW_REQUIRED`""
    },
    @{
        Name        = "gtip_hitl_questions"
        Description = "Musavire teknik ayrim sorusu yoneltilen kararlar"
        Filter      = "$base AND jsonPayload.decision_status=`"WAITING_FOR_USER`""
    },
    @{
        # Uluslararasi emsal aramasinin basarisizlik orani. Iki isi birden gorur:
        # (1) grounded arama ne siklikta 504 aliyor, (2) uydurma emsal uretiminin
        # geri gelmedigini izlemek icin bu logger'in tum uyarilarini yuzeye cikarir.
        # NOT: filtre degerlerinde BOSLUK kullanilmaz; PowerShell -> cmd.exe
        # argüman bölmesi tirnak icindeki boslukta filtreyi parcaliyor.
        Name        = "gtip_intl_search_failures"
        Description = "Uluslararasi emsal aramasi uyari/hatalari (grounded search saglik gostergesi)"
        Filter      = "$base AND jsonPayload.logger=`"InternationalSearchEngine`" AND severity>=WARNING"
    },
    @{
        # Fasil geri almasi: ilk fasil secimi hicbir pozisyonla eslesmedi.
        # Olcumde dogrulugu +3-4 puan artirdi ama p95 gecikmeyi 23s'den 41s'ye
        # cikardi (fazladan bir CHAPTER ~20k token + HEADING cagrisi). Bu oran
        # yukselirse gecikme bedeli de yukselir.
        Name        = "gtip_chapter_backtrack"
        Description = "Yanlis fasil secimi sonrasi geri alma (gecikme maliyeti gostergesi)"
        Filter      = "$base AND jsonPayload.message:`"backtracking`""
    },
    @{
        # Kullaniciya donen yavas yanitlar. Olcumde p95 41s gorulduk; kullanici
        # yuzeyinde bu kabul edilemez, esigi asan istek orani izlenmeli.
        Name        = "gtip_slow_analysis"
        Description = "20 saniyeyi asan siniflandirma analizleri"
        Filter      = "$base AND jsonPayload.stage=`"model_closed_set`" AND jsonPayload.duration_ms>20000"
    }
)

if (-not (Get-Command gcloud.cmd -ErrorAction SilentlyContinue)) { throw "gcloud.cmd bulunamadi." }

foreach ($metric in $metrics) {
    $name = $metric.Name
    & cmd.exe /c "gcloud.cmd logging metrics describe $name --project $ProjectId >nul 2>&1"
    $action = if ($LASTEXITCODE -eq 0) { "update" } else { "create" }
    $global:LASTEXITCODE = 0

    Write-Host "[$action] $name"
    & gcloud.cmd logging metrics $action $name `
        --project $ProjectId `
        --description $metric.Description `
        --log-filter $metric.Filter `
        --quiet
    Assert-LastExitCode "Log metrigi yapilandirilamadi: $name"
}

Write-Host ""
Write-Host "Metrikler hazir. Dogrulama (deploy sonrasi birkac analiz calistirdiktan sonra):"
Write-Host "  gcloud.cmd logging read '$base AND severity>=ERROR' --limit 10 --project $ProjectId"
Write-Host ""
Write-Host "Alarm politikalari, metrikler gercek dagilimi gosterecek kadar veri topladiktan"
Write-Host "sonra Cloud Monitoring uzerinden tanimlanmalidir."
