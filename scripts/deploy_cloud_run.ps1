[CmdletBinding()]
param(
    [string]$ProjectId = "gumruk-mevzuat",
    [string]$Region = "us-central1",
    [string]$Release = "",
    [string]$GoogleOAuthClientId = "",
    [string]$GoogleWorkspaceDomains = "",
    [string]$AdminEmails = "",
    [string]$SeniorBrokerEmails = "",
    [string]$IapAudience = "",
    [string[]]$AdditionalCorsOrigins = @(),
    [switch]$AllowPublicDemo,
    [switch]$AllowDirtyTree,
    [switch]$SkipLocalChecks,
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendService = "gtip-backend"
$WebService = "gtip-web"
$Repository = "gtip-repo"
$SqlInstanceName = "gumruk-db"
$CloudSqlConnection = "$ProjectId`:$Region`:$SqlInstanceName"
$Bucket = "$ProjectId-storage-$Region"
$RuntimeServiceAccount = "gtip-backend-sa@$ProjectId.iam.gserviceaccount.com"

function Assert-LastExitCode([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Gerekli komut bulunamadı: $Name"
    }
}

function Invoke-GcloudCheck([string]$CommandLine) {
    & cmd.exe /c "gcloud.cmd $CommandLine >nul 2>&1"
}

function Write-JsonFile([string]$Path, [object]$Value) {
    $json = $Value | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($Path, $json, [System.Text.UTF8Encoding]::new($false))
}

function Resolve-ImageDigest([string]$TaggedImage) {
    $digest = (& gcloud.cmd artifacts docker images describe $TaggedImage `
        --project $ProjectId `
        --format="value(image_summary.digest)").Trim()
    Assert-LastExitCode "İmaj digest'i çözümlenemedi: $TaggedImage"
    if ($digest -notmatch '^sha256:[0-9a-f]{64}$') {
        throw "Artifact Registry geçerli bir sha256 digest döndürmedi: $TaggedImage"
    }
    return "$($TaggedImage.Split(':')[0])@$digest"
}

function Get-ServiceDescription([string]$ServiceName) {
    $raw = & gcloud.cmd run services describe $ServiceName `
        --region $Region `
        --project $ProjectId `
        --format=json
    Assert-LastExitCode "Cloud Run servisi okunamadı: $ServiceName"
    return ($raw | ConvertFrom-Json)
}

function Get-TaggedUrl([string]$ServiceName, [string]$Tag) {
    $description = Get-ServiceDescription $ServiceName
    $traffic = @($description.status.traffic) | Where-Object { $_.tag -eq $Tag } | Select-Object -First 1
    if (-not $traffic -or -not $traffic.url) {
        throw "$ServiceName için '$Tag' candidate URL'i bulunamadı."
    }
    return [string]$traffic.url
}

function Wait-HttpOk([string]$Url, [int]$Attempts = 12) {
    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 30 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { return $response }
        } catch {
            $lastError = $_
        }
        Start-Sleep -Seconds 5
    }
    throw "Smoke test başarısız: $Url. Son hata: $lastError"
}

Assert-Command "gcloud.cmd"
Assert-Command "git"

Push-Location $RepoRoot
$BackendEnvFile = $null
$WebEnvFile = $null
$CorsFile = $null
try {
    if (-not $Release) {
        $Release = (& git rev-parse --short=12 HEAD).Trim()
        Assert-LastExitCode "Git release kimliği alınamadı."
    }
    if ($Release -notmatch '^[a-z0-9][a-z0-9-]{0,49}$') {
        throw "Release yalnız küçük harf, rakam ve tire içermeli; en fazla 50 karakter olmalıdır."
    }
    if (-not $AllowDirtyTree) {
        $dirty = & git status --porcelain
        Assert-LastExitCode "Git çalışma ağacı denetlenemedi."
        if ($dirty) {
            throw "Çalışma ağacı temiz değil. Değişiklikleri commit edin veya bilinçli olarak -AllowDirtyTree kullanın."
        }
    }
    if (-not $AllowPublicDemo -and -not $GoogleOAuthClientId -and -not $IapAudience) {
        throw "Erişim kapalı kalır: GoogleOAuthClientId/IapAudience verin veya bilinçli olarak -AllowPublicDemo kullanın."
    }

    if (-not $SkipLocalChecks) {
        Assert-Command ".\.venv\Scripts\python.exe"
        Assert-Command "npm.cmd"
        $env:ENVIRONMENT = "development"
        $env:USE_GCP_EMULATOR = "true"
        $env:GEMINI_API_KEY = "local-emulator-placeholder"
        $env:JWT_SECRET_KEY = "local-development-only"
        $testTemp = Join-Path ([System.IO.Path]::GetTempPath()) "gtip-test-$(New-Guid)"
        try {
            & .\.venv\Scripts\python.exe -m pytest api/tests -q -p no:cacheprovider --basetemp $testTemp
            Assert-LastExitCode "Backend testleri başarısız."
        } finally {
            if (Test-Path $testTemp) { Remove-Item -Recurse -Force $testTemp -ErrorAction SilentlyContinue }
        }
        & .\.venv\Scripts\python.exe -m compileall -q api scripts
        Assert-LastExitCode "Python compileall başarısız."
        & npm.cmd --prefix web ci --ignore-scripts
        Assert-LastExitCode "Frontend npm ci başarısız."
        & npm.cmd --prefix web run build
        Assert-LastExitCode "Frontend production build başarısız."
        & npm.cmd --prefix web audit --omit=dev --audit-level=high
        Assert-LastExitCode "Frontend production dependency audit başarısız."
    }

    Write-Host "GCP API ve üretim önkoşulları doğrulanıyor..."
    & gcloud.cmd services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com `
        sqladmin.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com `
        storage.googleapis.com containeranalysis.googleapis.com --project $ProjectId --quiet
    Assert-LastExitCode "Gerekli GCP API'leri etkinleştirilemedi."

    Invoke-GcloudCheck "artifacts repositories describe $Repository --location $Region --project $ProjectId"
    Assert-LastExitCode "Artifact Registry repository bulunamadı: $Repository"
    Invoke-GcloudCheck "iam service-accounts describe $RuntimeServiceAccount --project $ProjectId"
    Assert-LastExitCode "Runtime servis hesabı bulunamadı: $RuntimeServiceAccount"
    foreach ($secret in @("gtip-db-password", "gtip-jwt-secret")) {
        Invoke-GcloudCheck "secrets versions describe latest --secret $secret --project $ProjectId"
        Assert-LastExitCode "Secret'ın etkin latest sürümü bulunamadı: $secret"
    }

    $sqlRaw = & cmd.exe /c "gcloud.cmd sql instances describe $SqlInstanceName --project $ProjectId --format=json 2>nul"
    Assert-LastExitCode "Cloud SQL '$SqlInstanceName' bulunamadı. Boş instance oluşturulmayacak; önce final backup restore edilmelidir."
    $sql = $sqlRaw | ConvertFrom-Json
    if ($sql.state -ne "RUNNABLE") { throw "Cloud SQL hazır değil; state=$($sql.state)" }
    if ($sql.region -ne $Region -or $sql.databaseVersion -notlike "POSTGRES_15*") {
        throw "Cloud SQL bölge/sürüm uyuşmuyor: region=$($sql.region), version=$($sql.databaseVersion)"
    }
    if (-not $sql.settings.deletionProtectionEnabled) { throw "Cloud SQL deletion protection kapalı." }
    if (-not $sql.settings.storageAutoResize) { throw "Cloud SQL storage auto-growth kapalı." }
    if (-not $sql.settings.backupConfiguration.enabled -or -not $sql.settings.backupConfiguration.pointInTimeRecoveryEnabled) {
        throw "Cloud SQL backup/PITR etkin değil."
    }
    Invoke-GcloudCheck "sql databases describe gtip_db --instance $SqlInstanceName --project $ProjectId"
    Assert-LastExitCode "Restore edilen Cloud SQL içinde gtip_db bulunamadı."
    Invoke-GcloudCheck "storage buckets describe gs://$Bucket --project $ProjectId"
    Assert-LastExitCode "GCS bucket bulunamadı: gs://$Bucket"

    Write-Host "Least-privilege runtime IAM uygulanıyor..."
    foreach ($role in @("roles/aiplatform.user", "roles/cloudsql.client")) {
        Invoke-GcloudCheck "projects add-iam-policy-binding $ProjectId --member=serviceAccount:$RuntimeServiceAccount --role=$role --condition=None --quiet"
        Assert-LastExitCode "IAM rolü verilemedi: $role"
    }
    foreach ($secret in @("gtip-db-password", "gtip-jwt-secret")) {
        Invoke-GcloudCheck "secrets add-iam-policy-binding $secret --project $ProjectId --member=serviceAccount:$RuntimeServiceAccount --role=roles/secretmanager.secretAccessor --quiet"
        Assert-LastExitCode "Secret IAM verilemedi: $secret"
    }
    Invoke-GcloudCheck "storage buckets add-iam-policy-binding gs://$Bucket --member=serviceAccount:$RuntimeServiceAccount --role=roles/storage.objectAdmin --quiet"
    Assert-LastExitCode "Bucket object IAM verilemedi."
    Invoke-GcloudCheck "iam service-accounts add-iam-policy-binding $RuntimeServiceAccount --project $ProjectId --member=serviceAccount:$RuntimeServiceAccount --role=roles/iam.serviceAccountTokenCreator --quiet"
    Assert-LastExitCode "Signed URL için self signBlob yetkisi verilemedi."

    $BackendTag = "$Region-docker.pkg.dev/$ProjectId/$Repository/backend:$Release"
    $WebTag = "$Region-docker.pkg.dev/$ProjectId/$Repository/web:$Release"
    if (-not $SkipBuild) {
        Write-Host "Backend image build ediliyor: $BackendTag"
        & gcloud.cmd builds submit --tag $BackendTag --project $ProjectId --quiet .
        Assert-LastExitCode "Backend Cloud Build başarısız."
        Write-Host "Web image build ediliyor: $WebTag"
        & gcloud.cmd builds submit --tag $WebTag --project $ProjectId --quiet web
        Assert-LastExitCode "Web Cloud Build başarısız."
    }
    $BackendImage = Resolve-ImageDigest $BackendTag
    $WebImage = Resolve-ImageDigest $WebTag

    $PublicDemoValue = if ($AllowPublicDemo) { "true" } else { "false" }
    $BackendEnv = [ordered]@{
        GCP_PROJECT_ID = $ProjectId
        GCP_REGION = $Region
        VERTEX_AI_LOCATION = $Region
        ENVIRONMENT = "production"
        USE_GCP_EMULATOR = "false"
        GCS_BUCKET_NAME = $Bucket
        CLOUD_SQL_CONNECTION_NAME = $CloudSqlConnection
        INSTANCE_CONNECTION_NAME = $CloudSqlConnection
        DB_USER = "postgres"
        DB_NAME = "gtip_db"
        DB_POOL_SIZE = "1"
        DB_MAX_OVERFLOW = "1"
        WEB_CONCURRENCY = "2"
        PRIMARY_AI_MODEL = "gemini-2.5-flash"
        EXTRACTOR_LLM_MODEL = "gemini-2.5-flash-lite"
        REASONING_LLM_MODEL = "gemini-2.5-flash"
        AUDITOR_LLM_MODEL = "gemini-2.5-flash"
        EMBEDDING_MODEL = "text-embedding-005"
        CORS_ALLOWED_ORIGINS = ($AdditionalCorsOrigins -join ",")
        ALLOW_PUBLIC_DEMO_ACCESS = $PublicDemoValue
        PUBLIC_DEMO_RATE_LIMIT_PER_MINUTE = "10"
        PUBLIC_DEMO_UPLOAD_LIMIT_PER_MINUTE = "5"
        MAX_BATCH_ITEMS = "10"
        BATCH_CONCURRENCY = "4"
        SKIP_TGTC_AUTO_SEED = "true"
        GOOGLE_OAUTH_CLIENT_ID = $GoogleOAuthClientId
        GOOGLE_WORKSPACE_DOMAINS = $GoogleWorkspaceDomains
        ADMIN_EMAILS = $AdminEmails
        SENIOR_BROKER_EMAILS = $SeniorBrokerEmails
        IAP_AUDIENCE = $IapAudience
    }
    $BackendEnvFile = [System.IO.Path]::GetTempFileName()
    Write-JsonFile $BackendEnvFile $BackendEnv
    $CandidateTag = "candidate-$Release"

    Write-Host "Backend candidate revision deploy ediliyor..."
    $backendArgs = @(
        "run", "deploy", $BackendService, "--image", $BackendImage,
        "--region", $Region, "--project", $ProjectId, "--platform", "managed",
        "--allow-unauthenticated", "--execution-environment", "gen2",
        "--memory", "4Gi", "--cpu", "2", "--concurrency", "20",
        "--min-instances", "0", "--max-instances", "3", "--timeout", "300s",
        "--cpu-boost", "--service-account", $RuntimeServiceAccount,
        "--set-cloudsql-instances", $CloudSqlConnection,
        "--env-vars-file", $BackendEnvFile,
        "--set-secrets", "DB_PASS=gtip-db-password:latest,JWT_SECRET_KEY=gtip-jwt-secret:latest",
        "--startup-probe", "httpGet.path=/api/v1/ready,httpGet.port=8080,timeoutSeconds=10,periodSeconds=10,failureThreshold=18",
        "--readiness-probe", "httpGet.path=/api/v1/ready,httpGet.port=8080,timeoutSeconds=5,periodSeconds=10,failureThreshold=3,successThreshold=1",
        "--liveness-probe", "httpGet.path=/api/v1/health,httpGet.port=8080,initialDelaySeconds=30,timeoutSeconds=5,periodSeconds=30,failureThreshold=3",
        "--labels", "app=gtip,component=backend,release=$Release",
        "--tag", $CandidateTag, "--no-traffic", "--deploy-health-check", "--quiet"
    )
    & gcloud.cmd @backendArgs
    Assert-LastExitCode "Backend candidate deploy başarısız."
    $BackendCandidateUrl = Get-TaggedUrl $BackendService $CandidateTag
    $ready = Wait-HttpOk "$BackendCandidateUrl/api/v1/ready"
    $readyJson = $ready.Content | ConvertFrom-Json
    if ($readyJson.status -ne "ready" -or $readyJson.database -ne "healthy") {
        throw "Backend readiness beklenen içeriği döndürmedi: $($ready.Content)"
    }
    Wait-HttpOk "$BackendCandidateUrl/api/v1/health" | Out-Null
    & gcloud.cmd run services update-traffic $BackendService --region $Region --project $ProjectId `
        --to-tags "$CandidateTag=100" --quiet
    Assert-LastExitCode "Backend candidate trafiğe alınamadı."
    $BackendUrl = [string](Get-ServiceDescription $BackendService).status.url
    Wait-HttpOk "$BackendUrl/api/v1/ready" | Out-Null

    $BackendHost = ([Uri]$BackendUrl).Host
    $WebEnvFile = [System.IO.Path]::GetTempFileName()
    Write-JsonFile $WebEnvFile ([ordered]@{ BACKEND_ORIGIN = $BackendUrl; BACKEND_HOST = $BackendHost })
    Write-Host "Web candidate revision deploy ediliyor..."
    $webArgs = @(
        "run", "deploy", $WebService, "--image", $WebImage,
        "--region", $Region, "--project", $ProjectId, "--platform", "managed",
        "--allow-unauthenticated", "--execution-environment", "gen2",
        "--memory", "512Mi", "--cpu", "1", "--concurrency", "80",
        "--min-instances", "0", "--max-instances", "5", "--timeout", "300s",
        "--env-vars-file", $WebEnvFile,
        "--startup-probe", "httpGet.path=/healthz,httpGet.port=8080,timeoutSeconds=5,periodSeconds=5,failureThreshold=12",
        "--readiness-probe", "httpGet.path=/healthz,httpGet.port=8080,timeoutSeconds=5,periodSeconds=10,failureThreshold=3,successThreshold=1",
        "--liveness-probe", "httpGet.path=/healthz,httpGet.port=8080,initialDelaySeconds=10,timeoutSeconds=5,periodSeconds=30,failureThreshold=3",
        "--labels", "app=gtip,component=web,release=$Release",
        "--tag", $CandidateTag, "--no-traffic", "--deploy-health-check", "--quiet"
    )
    & gcloud.cmd @webArgs
    Assert-LastExitCode "Web candidate deploy başarısız."
    $WebCandidateUrl = Get-TaggedUrl $WebService $CandidateTag
    Wait-HttpOk "$WebCandidateUrl/healthz" | Out-Null
    Wait-HttpOk "$WebCandidateUrl/api/v1/health" | Out-Null
    & gcloud.cmd run services update-traffic $WebService --region $Region --project $ProjectId `
        --to-tags "$CandidateTag=100" --quiet
    Assert-LastExitCode "Web candidate trafiğe alınamadı."
    $WebUrl = [string](Get-ServiceDescription $WebService).status.url
    Wait-HttpOk $WebUrl | Out-Null
    Wait-HttpOk "$WebUrl/api/v1/health" | Out-Null

    $corsOrigins = @($WebUrl) + @($AdditionalCorsOrigins) | Where-Object { $_ } | Select-Object -Unique
    $CorsFile = [System.IO.Path]::GetTempFileName()
    Write-JsonFile $CorsFile @(@{
        origin = @($corsOrigins)
        method = @("PUT")
        responseHeader = @("Content-Type", "ETag")
        maxAgeSeconds = 3600
    })
    & gcloud.cmd storage buckets update "gs://$Bucket" --project $ProjectId `
        --pap `
        --lifecycle-file="$PSScriptRoot/gcs_lifecycle.json" `
        --cors-file=$CorsFile --quiet
    Assert-LastExitCode "GCS güvenlik/lifecycle/CORS yapılandırması başarısız."

    # Önce dar roller verildi; varsa eski geniş proje rollerini kaldır.
    foreach ($broadRole in @("roles/storage.admin", "roles/secretmanager.secretAccessor")) {
        $hasRole = & gcloud.cmd projects get-iam-policy $ProjectId `
            --flatten="bindings[].members" `
            --filter="bindings.role=$broadRole AND bindings.members=serviceAccount:$RuntimeServiceAccount" `
            --format="value(bindings.role)"
        Assert-LastExitCode "Proje IAM denetlenemedi: $broadRole"
        if (($hasRole | Out-String).Trim()) {
            Invoke-GcloudCheck "projects remove-iam-policy-binding $ProjectId --member=serviceAccount:$RuntimeServiceAccount --role=$broadRole --condition=None --quiet"
            Assert-LastExitCode "Geniş IAM rolü kaldırılamadı: $broadRole"
        }
    }

    Write-Host ""
    Write-Host "Servis dağıtımı tamamlandı."
    Write-Host "Release       : $Release"
    Write-Host "Backend image : $BackendImage"
    Write-Host "Web image     : $WebImage"
    Write-Host "Backend URL   : $BackendUrl"
    Write-Host "Web URL       : $WebUrl"
    Write-Host "Sonraki adım  : deploy_etl_jobs.ps1 ve deploy_tgtc_seed_job.ps1 komutlarına aynı backend digest'i verin."
} finally {
    foreach ($path in @($BackendEnvFile, $WebEnvFile, $CorsFile)) {
        if ($path -and (Test-Path -LiteralPath $path)) { Remove-Item -LiteralPath $path -Force }
    }
    Pop-Location
}
