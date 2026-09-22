# GTİP Tespit ve Karar Destek Sistemi

FastAPI backend, React/Vite arayüz ve TGTC/BTB veri işleme araçları.
Üretim mimarisi ve veri kaynakları için [mimari rapora](gcp_architecture_report.md) bakın.

## Yerel geliştirme (Windows / PowerShell)

Proje kökünde Python sanal ortamını hazırlayın:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r api/requirements.txt
```

Backend'i çevrimdışı geliştirme modunda başlatın:

```powershell
$env:ENVIRONMENT = 'development'
$env:USE_GCP_EMULATOR = 'true'
$env:GEMINI_API_KEY = 'local-emulator-placeholder'
$env:JWT_SECRET_KEY = 'local-development-only'
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Bu değerler yalnızca yerel emülatör içindir. Gerçek model erişimi sağlamaz.
Yerel veri/kanıt eksik olduğunda uygulamanın manuel inceleme istemesi beklenir.
Canlı model ve Cloud SQL doğrulaması ayrıca yetkili GCP yapılandırması gerektirir.

İkinci terminalde arayüzü başlatın:

```powershell
cd web
npm.cmd ci
npm.cmd run dev
```

Arayüz: `http://localhost:5173`. API sağlık kontrolü: `http://127.0.0.1:8000/api/v1/health`.
Geliştirme arayüzü varsayılan olarak `/api/v1` üzerinden yerel backend'e gider.
Backend başka porttaysa `API_PROXY_TARGET=http://127.0.0.1:PORT` ayarlayın.
`VITE_API_URL` ayarlanırsa tam API taban adresi olarak kullanılır (ör. `https://example.com/api/v1`).
Üretimde tarayıcı `/api/v1` yolunu kullanır; web container'ındaki Nginx bu yolu
`BACKEND_ORIGIN` değerine proxy eder. Böylece web imajına ortam URL'si gömülmez.

## Doğrulama

Proje kökünde temel derleme kontrolleri:

```powershell
.\.venv\Scripts\python.exe -m compileall -q api scripts
npm.cmd --prefix web run build
```

## Doğruluk ölçümü (benchmark)

Prompt, retrieval veya model ayarı değiştiren her çalışma **önce ve sonra** ölçülmelidir.
Ground truth elle yazılmış örnekler değil, Cloud SQL'deki gerçek Ticaret Bakanlığı BTB
kararlarıdır; her kayıt bir (ürün açıklaması, resmî GTİP) çiftidir. Numunenin kendi
kararı emsal havuzundan çıkarılarak sızıntı önlenir.

Benchmark canlı Vertex AI ve Cloud SQL erişimi ister; bu yüzden CI kapısı **değildir**.
Birincil yol, üretim imajıyla çalışan Cloud Run Job'udur:

```powershell
gcloud.cmd run jobs execute gtip-benchmark --region us-central1 --project gumruk-mevzuat --wait
gcloud.cmd logging read 'resource.labels.job_name="gtip-benchmark"' --limit 80 --format='value(textPayload)'
```

Yerelde çalıştırmak için Cloud SQL Auth Proxy ve ADC gerekir:

```powershell
gcloud.cmd auth application-default login
.\cloud-sql-proxy.exe gumruk-mevzuat:us-central1:gumruk-db --port 5432
# ikinci terminalde
$env:ENVIRONMENT = 'production'
$env:DATABASE_URL = 'postgresql+psycopg2://postgres:<parola>@127.0.0.1:5432/gtip_db'
.\.venv\Scripts\python.exe -m scripts.evaluate_gtip_benchmark --sample 300
```

Sonuç `benchmark_results/benchmark-<zaman>.json` altına yazılır. Bir önceki ölçümle
karşılaştırmak için:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_gtip_benchmark --sample 300 `
  --baseline benchmark_results/<baseline-dosyası>.json
```

Doğruluk (`leaf_acc`, `heading_acc`) ile kapsam (`coverage`, `hitl_rate`) ayrı
raporlanır: modelin soru sorması bir sınıflandırma hatası değildir, kapsam kaybıdır.

### Kanıt bayrakları ve ablasyon ölçümü

Seçim promptuna giren üç kanıt ayrı ayrı kapatılabilir:

| Bayrak | Ne enjekte eder |
|---|---|
| `SELECTION_USE_RAW_TEXT` | Ham müşteri beyanı (özellik çıkarımıyla damıtılmadan) |
| `SELECTION_USE_PRECEDENTS` | Seviyeyle eşleşen BTB/EBTI emsalleri |
| `SELECTION_USE_CHAPTER_NOTES` | İlgili faslın resmî notları (GİR 1 dışlama hükümleri) |

Bu, her maddenin doğruluk katkısını tek tek ölçmeyi sağlar; aynı zamanda bir madde
üretimde doğruluğu düşürürse yeniden deploy etmeden kapatma imkânı verir.

Ölçüm sırası — **önce baseline**, sonra maddeler tek tek eklenir:

```powershell
# 1. Baseline: tüm kanıt kapalı (kanıt zinciri öncesi davranış)
gcloud.cmd run jobs execute gtip-benchmark --region us-central1 --args='-m,scripts.evaluate_gtip_benchmark,--sample,300,--baseline-run' --wait

# 2. Yalnız ham beyan açık
... --args='-m,scripts.evaluate_gtip_benchmark,--sample,300,--ablate,SELECTION_USE_PRECEDENTS,--ablate,SELECTION_USE_CHAPTER_NOTES'

# 3. Ham beyan + emsaller
... --args='-m,scripts.evaluate_gtip_benchmark,--sample,300,--ablate,SELECTION_USE_CHAPTER_NOTES'

# 4. Hepsi açık (varsayılan üretim davranışı)
... --args='-m,scripts.evaluate_gtip_benchmark,--sample,300'
```

Her rapor hangi bayrakların açık olduğunu `evidence_flags` alanında saklar; karşılaştırma
çıktısı iki ölçümün bayrak farkını da yazar. Bir adım `leaf_acc` veya `heading_acc`
değerini düşürürse o bayrak üretimde `false` bırakılır.

## GCP üretim dağıtımı

Dağıtım betikleri boş veritabanı oluşturmaz ve `latest` etiketiyle deploy etmez.
Önce değişiklikleri commit edin; ana betik kirli çalışma ağacında varsayılan olarak durur.

Silinen Cloud SQL'i FINAL backup'tan yeni, regional HA instance olarak geri yüklemek için:

```powershell
.\scripts\restore_cloud_sql.ps1 `
  -BackupName 'projects/gumruk-mevzuat/backups/44b82d7b-85fe-4e5c-b30f-bc6fee0106e4'
```

Servisleri immutable image digest, candidate revision ve otomatik smoke test ile yayınlayın.
Kimlik doğrulama henüz yapılandırılmadıysa public demo erişimi ancak açık bir parametreyle açılır:

```powershell
.\scripts\deploy_cloud_run.ps1 -AllowPublicDemo
```

Komut sonunda yazılan backend `@sha256:...` değerini dört job için aynen kullanın:

```powershell
$release = git rev-parse --short=12 HEAD
$backendImage = '<deploy çıktısındaki backend @sha256 digest>'
.\scripts\deploy_etl_jobs.ps1 -Image $backendImage -Release $release
.\scripts\deploy_tgtc_seed_job.ps1 -Image $backendImage -Release $release
.\scripts\verify_deployment.ps1
```

ETL betiği iki scheduler'ı güvenlik amacıyla `PAUSED` bırakır. Daily ve BTB job'ları
elle başarılı çalıştırıldıktan sonra scheduler'ları resume edin ve son kontrolü çalıştırın:

```powershell
gcloud.cmd scheduler jobs resume resmi-gazete-daily-sync --location us-central1 --project gumruk-mevzuat
gcloud.cmd scheduler jobs resume official-btb-daily-sync --location us-central1 --project gumruk-mevzuat
.\scripts\verify_deployment.ps1 -RequireSchedulersEnabled
```

### Rollback

Trafik önceki revizyona anında geri alınabilir; eski revizyonlar silinmez:

```powershell
gcloud.cmd run revisions list --service gtip-backend --region us-central1 --project gumruk-mevzuat
gcloud.cmd run services update-traffic gtip-backend --region us-central1 --project gumruk-mevzuat `
  --to-revisions '<önceki-revizyon-adı>=100'
```

Dağıtım betiği trafiği kaydırdıktan sonra eski `candidate-*` etiketlerini temizler.
Etiketli revizyonlar `min-instances=1` ile adreslenebilir kaldığında trafik almasalar
bile sürekli açık instance olarak faturalanır.

Ayrıntılı geri yükleme, IAM, smoke test ve rollback kapıları için
[GCP dağıtım planına](gcp_deploy_plan.md) bakın.

## Git bağlantısı

Depo: https://github.com/yusufarbc/yapay-zeka-gtip-tespiti

```powershell
git status --short --branch
git remote -v
git fsck --full
```

8 Eylül 2026'da kayıp `.git` metadata'sı GitHub geçmişinden geri yüklendi;
`main` dalı `origin/main` dalını izliyor. Çalışma dosyaları korunarak kurtarma yapıldı.
