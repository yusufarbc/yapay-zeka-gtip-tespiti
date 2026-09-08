$ErrorActionPreference = "Stop"

$PROJECT_ID = "gumruk-mevzuat"
$REGION = "us-central1"
$WEB_IMAGE_URI = "$REGION-docker.pkg.dev/$PROJECT_ID/gtip-repo/web:latest"

Write-Host "Frontend image derleniyor: $WEB_IMAGE_URI"
& gcloud.cmd builds submit --tag $WEB_IMAGE_URI ./web --project $PROJECT_ID
if ($LASTEXITCODE -ne 0) { throw "Web Cloud Build başarısız." }

Write-Host "Frontend Cloud Run'a dağıtılıyor..."
& gcloud.cmd run deploy gtip-web `
    --image $WEB_IMAGE_URI `
    --region $REGION `
    --project $PROJECT_ID `
    --platform managed `
    --allow-unauthenticated `
    --memory 512Mi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 10 `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Web Cloud Run dağıtımı başarısız." }

& gcloud.cmd run services describe gtip-web --region $REGION --project $PROJECT_ID --format="value(status.url)"
