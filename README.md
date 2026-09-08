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
Üretim Docker derlemesi mevcut Cloud Run API adresini kullanır.

## Doğrulama

Yukarıdaki yerel backend ortam değişkenleri ayarlanmışken proje kökünde:

```powershell
.\.venv\Scripts\python.exe -m pip install -r api/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest api/tests -q -p no:cacheprovider
npm.cmd --prefix web run build
```

`api/tests` otomatik regresyon testlerini içerir. `scripts/test_*.py` dosyaları
harici veri kaynaklarına/PDF dosyalarına erişebilen elle çalıştırılan tarama araçlarıdır.

## Git bağlantısı

Depo: https://github.com/yusufarbc/yapay-zeka-gtip-tespiti

```powershell
git status --short --branch
git remote -v
git fsck --full
```

8 Eylül 2026'da kayıp `.git` metadata'sı GitHub geçmişinden geri yüklendi;
`main` dalı `origin/main` dalını izliyor. Çalışma dosyaları korunarak kurtarma yapıldı.
