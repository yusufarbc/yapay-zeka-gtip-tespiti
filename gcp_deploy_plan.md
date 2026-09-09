# GCP Üretim Dağıtım Planı

Tarih: 9 Eylül 2026  
Hedef proje: `gumruk-mevzuat`  
Hedef bölge: `us-central1`  
Planlanan sürüm: deployment hazırlık değişiklikleri commit edildikten sonraki SHA

## 1. Karar özeti

Mevcut durum **NO-GO**. Uygulama testleri başarılıdır; ancak üretim altyapısı dağıtıma hazır değildir.

Dağıtımdan önce çözülmesi gereken zorunlu maddeler:

1. Silinen `gumruk-db` instance'ı yeni ve boş oluşturulmamalı; mevcut FINAL yedekten geri yüklenmelidir.
2. Bucket CORS yapılandırması ve servis hesabının `iam.serviceAccounts.signBlob` yetkisi eklenmeden tarayıcıdan dosya yükleme çalışmaz.
3. Billing durumu doğrulanmalıdır. Cloud Billing API kapalı olduğu için CLI denetimi tamamlanamamıştır.
4. En son commit için yeni backend ve web imajları üretilmelidir. Registry'deki mevcut imajlar son committen eskidir.
5. Cloud Run servis/job'ları yeniden oluşturulmadan scheduler görevleri çalıştırılmamalıdır.

Kod tarafındaki P0/P1 deploy açıkları giderildi: güvenli restore için ayrı betik,
immutable digest deploy, candidate smoke test/traffic promotion, HTTP probe'ları,
runtime Nginx API proxy, daraltılmış IAM uygulaması, GCS CORS/lifecycle kurulumu ve
hash'li Python bağımlılık kilidi eklendi. Canlı GCP maddeleri uygulanıp doğrulanana
kadar genel durum yine **NO-GO** kalır.

## 2. Doğrulanmış mevcut durum

### Uygulama

- Git çalışma ağacı temiz; `main` ve `origin/main` aynı committe.
- Backend: 80/80 pytest başarılı.
- Frontend: `npm ci` ve Vite production build başarılı.
- Frontend bağımlılık denetimi: 0 bilinen açık.
- Üretim `api/requirements.txt` temiz çözümlemesi: 0 bilinen açık.
- Python `pip check` ve `compileall`: başarılı.
- Tüm PowerShell dağıtım betikleri sözdizimsel olarak geçerli.
- Yerel Docker daemon çalışmadığı için yerel container build yapılmadı. Önceki Cloud Build çalışmaları başarılı olsa da güncel commit için build yok.

### GCP

- Proje aktif; aktif hesap proje Owner yetkisine sahip.
- Gerekli temel API'ler aktif: Cloud Run, Cloud Build, Artifact Registry, Cloud SQL Admin, Secret Manager, Vertex AI, Cloud Scheduler, Storage, Logging ve Monitoring.
- `gtip-repo`, GCS bucket, iki secret ve runtime servis hesabı mevcut.
- `gtip-db-password`: iki etkin sürüm; `gtip-jwt-secret`: bir etkin sürüm.
- Cloud Run servisleri ve dört Cloud Run Job 9 Eylül 2026 01:47 TRT'de silinmiş.
- `gumruk-db` 9 Eylül 2026 01:48 TRT'de final backup alınarak silinmiş.
- FINAL backup:
  - Ad: `projects/gumruk-mevzuat/backups/44b82d7b-85fe-4e5c-b30f-bc6fee0106e4`
  - Kaynak: PostgreSQL 15 / `gumruk-db` / `us-central1`
  - Son kullanım: `2026-10-08T22:48:38.465Z` (9 Ekim 2026 01:48 TRT)
- İki scheduler hâlâ etkin fakat hedef job'lar yok. Son denemeler `PERMISSION_DENIED` (`status.code=7`) ile sonuçlanmış.
- Bucket'ta uniform access açık; fakat public access prevention `inherited`, CORS ve lifecycle uygulanmış görünmüyor.
- Runtime servis hesabında proje düzeyinde `storage.admin` bulunuyor; signed URL için gereken self `signBlob` yetkisi yok.
- Container Analysis API kapalı; registry imajı güvenlik taraması yapılamıyor.
- Mimari rapordaki “servisler/job'lar/Cloud SQL çalışıyor” ifadesi artık fiili durumu yansıtmıyor.

## 3. Kod ve dağıtım riskleri

### P0 — dağıtımı durduranlar

1. `scripts/deploy_cloud_run.ps1`, Cloud SQL yoksa boş `gumruk-db` oluşturuyor. Bu çalıştırılırsa final backup'taki üretim verisi otomatik geri gelmez.
2. Yeni oluşturulan boş instance'ın `postgres` parolası ile mevcut `gtip-db-password` secret'ının eşleşmesini sağlayan bir adım yoktur.
3. Tarayıcı web origin'inden GCS'e doğrudan `PUT` yapıyor; bucket CORS kuralı yoktur.
4. Cloud Run ADC kimliğiyle V4 signed URL üretimi için servis hesabında `iam.serviceAccounts.signBlob` izni yoktur.
5. Scheduler'lar var olmayan job'lara istek atmaya devam etmektedir.

### P1 — üretim kalitesi

1. `db-f1-micro` test/geliştirme sınıfıdır ve Cloud SQL SLA kapsamında değildir. Üretim için dedicated CPU + regional HA önerilir.
2. Python bağımlılıkları `api/requirements.lock.txt` içinde Linux/Python 3.11 için hash'li kilitlenmiştir; kullanılmayan ve eski `pypdf` bağımlılığı kaldırılmıştır.
3. İmajlar commit etiketiyle build edilir, Artifact Registry digest'ine çözülür ve servis/job'lara immutable digest ile verilir.
4. Frontend `/api` isteklerini runtime'da `BACKEND_ORIGIN` değerine Nginx ile proxy eder; build-time URL bağımlılığı kaldırılmıştır.
5. Backend ve web deploy komutlarında startup/readiness/liveness probe'ları tanımlanmıştır.
6. Uygulama DB başlangıç hatalarını non-blocking olarak yutuyor; `/health` DB'yi kontrol etmiyor. Trafik öncesi `/api/v1/ready` zorunlu kapı olmalıdır.
7. `ALLOW_PUBLIC_DEMO_ACCESS=true` ve instance-içi rate limiter çoklu instance'larda küresel kota sağlamaz. Maliyet/kötüye kullanım riski için Cloud Armor/API Gateway veya paylaşımlı sayaç değerlendirilmelidir.
8. `storage.admin` proje düzeyinde gereğinden geniştir. Bucket düzeyinde object izinlerine daraltılmalıdır.
9. `GOOGLE_OAUTH_CLIENT_ID`, domain/admin allowlist veya IAP audience deploy betiğinde ayarlanmıyor. Yönetim endpointlerinin gerçek kimlik akışı ayrıca yapılandırılmalıdır.
10. Backend imajına yalnız iki üretilmiş TGTC JSON'u alınır; ham PDF/XLS/CSV ve test/deploy araçları build context'inden çıkarılmıştır.

## 4. Uygulama sırası

Aşağıdaki komutlar altyapıyı değiştirir; yalnızca değişiklik penceresinde ve ayrı onayla çalıştırılmalıdır.

### Faz A — değişiklik penceresi ve önkoşullar

```powershell
$PROJECT_ID = 'gumruk-mevzuat'
$REGION = 'us-central1'
$RELEASE = '7d5f173'
$SA = "gtip-backend-sa@$PROJECT_ID.iam.gserviceaccount.com"
$BACKUP = 'projects/gumruk-mevzuat/backups/44b82d7b-85fe-4e5c-b30f-bc6fee0106e4'

gcloud.cmd config set project $PROJECT_ID
gcloud.cmd config set run/region $REGION

gcloud.cmd scheduler jobs pause resmi-gazete-daily-sync --location $REGION --project $PROJECT_ID
gcloud.cmd scheduler jobs pause official-btb-daily-sync --location $REGION --project $PROJECT_ID
```

Kontroller:

- Billing Console'da projenin aktif billing hesabına bağlı olduğunu doğrula; istenirse Cloud Billing API'yi etkinleştirip CLI ile de doğrula.
- FINAL backup adını ve son kullanım tarihini yeniden doğrula.
- Dağıtım boyunca scheduler'ları `PAUSED` tut.

### Faz B — Cloud SQL'i final yedekten kurtar

Önerilen üretim profili: PostgreSQL 15, regional HA, en az iki dedicated vCPU, PITR, otomatik storage growth ve deletion protection.

```powershell
gcloud.cmd sql backups restore $BACKUP `
  --restore-instance=gumruk-db `
  --project=$PROJECT_ID `
  --region=$REGION `
  --database-version=POSTGRES_15 `
  --tier=db-custom-2-7680 `
  --availability-type=regional `
  --enable-point-in-time-recovery `
  --backup-start-time=00:00 `
  --storage-auto-increase `
  --deletion-protection `
  --final-backup `
  --final-backup-retention-days=30
```

Maliyet öncelikli demo ortamında daha küçük/zonal profil seçilebilir; bunun SLA sağlamadığı açıkça kabul edilmelidir.

Geri yükleme sonrası:

```powershell
gcloud.cmd sql instances describe gumruk-db --project $PROJECT_ID
gcloud.cmd sql databases list --instance gumruk-db --project $PROJECT_ID
gcloud.cmd sql users list --instance gumruk-db --project $PROJECT_ID
```

Önemli: Backup, veritabanlarını ve kullanıcıları geri yükler. `gtip-db-password` değiştirilmeden önce geri yüklenen kullanıcının mevcut secret ile bağlantısı test edilmelidir. Boş database oluşturma veya seed çalıştırma bu kontrolden önce yapılmamalıdır.

### Faz C — GCS ve IAM düzeltmeleri

1. `scripts/gcs_cors.json` dosyasını gerçek web origin'leriyle oluştur:

```json
[
  {
    "origin": [
      "https://gtip-web-141090733173.us-central1.run.app",
      "https://gtip-web-gu6pxpqefa-uc.a.run.app"
    ],
    "method": ["PUT"],
    "responseHeader": ["Content-Type", "ETag"],
    "maxAgeSeconds": 3600
  }
]
```

2. Bucket politikasını uygula:

```powershell
gcloud.cmd storage buckets update gs://gumruk-mevzuat-storage-us-central1 `
  --public-access-prevention=enforced `
  --lifecycle-file=scripts/gcs_lifecycle.json `
  --cors-file=scripts/gcs_cors.json
```

3. Runtime hesabının kendi adına signed URL üretebilmesini sağla:

```powershell
gcloud.cmd iam service-accounts add-iam-policy-binding $SA `
  --project $PROJECT_ID `
  --member="serviceAccount:$SA" `
  --role='roles/iam.serviceAccountTokenCreator'
```

4. Önce bucket düzeyinde gereken object rollerini ver; işlev testinden sonra proje düzeyindeki `roles/storage.admin` rolünü kaldır. Secret accessor rolünü de yalnız kullanılan secret'lara daralt.

### Faz D — tekrarlanabilir release build

Kod değişikliği olarak:

1. `api/requirements.lock.txt` hash'li kilidi ve Dockerfile `--require-hashes` kurulumu eklendi.
2. Kullanılmayan `pypdf`, `openpyxl`, Cloud Scheduler ve doğrudan Secret Manager istemci bağımlılıkları kaldırıldı.
3. `deploy_cloud_run.ps1`, Cloud SQL yoksa güvenli biçimde durur; restore ayrı ve overwrite etmeyen `restore_cloud_sql.ps1` betiğindedir.
4. Build/deploy betikleri commit release etiketi üretir ve tag yerine çözümlenmiş digest kullanır.
5. Frontend same-origin `/api` Nginx proxy tasarımına geçirildi.
6. Cloud Run startup/readiness/liveness probe'ları eklendi.

Sonra doğrulama ve build:

```powershell
$env:ENVIRONMENT = 'development'
$env:USE_GCP_EMULATOR = 'true'
$env:GEMINI_API_KEY = 'local-emulator-placeholder'
$env:JWT_SECRET_KEY = 'local-development-only'

.\.venv\Scripts\python.exe -m pytest api/tests -q -p no:cacheprovider
npm.cmd --prefix web ci
npm.cmd --prefix web run build

.\scripts\deploy_cloud_run.ps1 -Release $RELEASE -AllowPublicDemo
```

Container Analysis API etkinleştirilerek iki release imajında HIGH/CRITICAL bulgu olmadığı doğrulanmalıdır. Dağıtımda tag yerine mümkünse build çıktısındaki immutable digest kullanılmalıdır.

### Faz E — backend candidate ve smoke test

Backend'i yeni servis olarak candidate tag ile, henüz ana trafiğe vermeden deploy et. Mevcut env/secrets yanında aşağıdakiler açıkça bulunmalıdır:

- `ENVIRONMENT=production`
- `USE_GCP_EMULATOR=false`
- `CLOUD_SQL_CONNECTION_NAME=gumruk-mevzuat:us-central1:gumruk-db`
- `DB_USER=postgres`, `DB_NAME=gtip_db`
- `DB_POOL_SIZE=1`, `DB_MAX_OVERFLOW=1`, `WEB_CONCURRENCY=2`
- gerçek `CORS_ALLOWED_ORIGINS`
- bilinçli karar verilmiş `ALLOW_PUBLIC_DEMO_ACCESS`
- `DB_PASS` ve `JWT_SECRET_KEY` Secret Manager bağlantıları
- `/api/v1/ready` startup/readiness probe

Smoke test kapıları:

1. `/api/v1/health` → 200 ve `production`.
2. `/api/v1/ready` → 200 ve `database=healthy`.
3. DB tablo/satır sayıları final backup öncesi beklenen değerlerle uyumlu.
4. CORS preflight yalnız web origin'ine izin veriyor.
5. `generate-upload-url` signed URL üretiyor; tarayıcı benzeri `PUT` başarılı; nesne okunup analiz edilebiliyor.
6. Metin analizi, görsel/PDF analizi, HITL, PDF export ve audit akışları uçtan uca başarılı.
7. Yetkisiz admin isteği 403/401; yetkili admin isteği başarılı.
8. Loglarda secret, token veya DB parolası yok.

Tüm kapılar geçince backend trafiğini candidate revision'a taşı.

### Faz F — frontend, job'lar ve scheduler

1. Gerçek backend URL ile web imajını build et.
2. Web candidate deploy et; ana sayfa, API çağrısı, upload ve hata ekranlarını smoke test et.
3. `gtip-archive-backfill`, `gtip-daily-sync`, `gtip-official-btb-sync` ve `gtip-seed-tgtc-2026` job'larını aynı backend release digest'iyle oluştur.
4. Her job için runtime SA'ya job düzeyinde `roles/run.invoker` ver.
5. Restore edilen DB'de TGTC verisi varsa seed job çalıştırma. Eksikse önce dry-run/satır sayısı kontrolü yap, sonra tek sefer çalıştır.
6. Daily ve BTB job'larını birer kez elle çalıştır, execution sonucu ve loglarını doğrula.
7. Yalnız başarılı manuel çalıştırmalardan sonra scheduler'ları resume et:

```powershell
gcloud.cmd scheduler jobs resume resmi-gazete-daily-sync --location $REGION --project $PROJECT_ID
gcloud.cmd scheduler jobs resume official-btb-daily-sync --location $REGION --project $PROJECT_ID
```

## 5. Go-live kabul ölçütleri

- [ ] Billing aktif ve bütçe/uyarı tanımlı.
- [ ] FINAL backup'tan Cloud SQL restore tamamlandı; veri sayıları doğrulandı.
- [ ] Cloud SQL deletion protection, PITR, backup ve storage auto-growth açık.
- [ ] GCS PAP, lifecycle ve CORS doğru.
- [ ] Signed URL ve gerçek browser upload başarılı.
- [ ] Runtime IAM least-privilege incelemesi tamamlandı.
- [ ] Güncel commit-tagged backend/web imajları build ve taramadan geçti.
- [ ] Backend `/health` ve `/ready` başarılı.
- [ ] Uçtan uca metin, dosya, HITL, rapor ve audit smoke testleri başarılı.
- [ ] Dört job mevcut; daily ve BTB manuel execution başarılı.
- [ ] Scheduler status temiz ve hedef URI'ler mevcut job'lara gidiyor.
- [ ] Cloud Logging hata alarmı, Cloud Run 5xx/latency alarmı, Cloud SQL CPU/storage/connection alarmları tanımlı.
- [ ] Rollback digest'leri ve DB kurtarma prosedürü kaydedildi.

## 6. Rollback

- Cloud Run: Trafiği önceki doğrulanmış digest'e taşı; `latest` kullanma.
- Frontend: Önceki web digest'ini yeniden deploy et.
- Job: Scheduler'ları pause et; job image'ını önceki digest'e döndür.
- Database: Canlı hedefe aceleyle backup restore ederek üzerine yazma. Yeni bir kurtarma instance'ı aç, veriyi doğrula ve kontrollü geçiş yap.
- İlk release'te eski Cloud Run revision olmadığı için Artifact Registry'deki doğrulanmış digest'ler tek servis rollback kaynağıdır.

## 7. Resmî GCP referansları

- [Cloud SQL silinen instance ve final backup kurtarma](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Cloud SQL backup restore komutu](https://docs.cloud.google.com/sdk/gcloud/reference/sql/backups/restore)
- [Cloud Run kademeli rollout ve rollback](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [Cloud Run health checks](https://docs.cloud.google.com/run/docs/configuring/healthchecks)
- [Cloud Storage signed URL için signBlob yetkisi](https://docs.cloud.google.com/storage/docs/access-control/signing-urls-with-helpers)
- [Cloud Storage CORS yapılandırması](https://docs.cloud.google.com/storage/docs/cors-configurations)
- [Cloud SQL instance boyutlandırma ve SLA notları](https://docs.cloud.google.com/sql/docs/postgres/instance-settings)
- [Cloud Build user-specified service account](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
