import os
import logging

logger = logging.getLogger(__name__)

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseModel as BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "GTİP Tespit ve Karar Destek Sistemi API"
    VERSION: str = "1.1.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    USE_GCP_EMULATOR: bool = os.getenv("USE_GCP_EMULATOR", "false").lower() == "true"
    ALLOW_PUBLIC_DEMO_ACCESS: bool = os.getenv("ALLOW_PUBLIC_DEMO_ACCESS", "false").lower() == "true"

    # Kimlik doğrulama. Google token'ları yalnızca beklenen OAuth client audience'i
    # ile kabul edilir; yönetici rolleri e-posta allowlist'iyle verilir.
    GOOGLE_OAUTH_CLIENT_ID: str = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    GOOGLE_WORKSPACE_DOMAINS: str = os.getenv("GOOGLE_WORKSPACE_DOMAINS", "").strip()
    ADMIN_EMAILS: str = os.getenv("ADMIN_EMAILS", "").strip()
    SENIOR_BROKER_EMAILS: str = os.getenv("SENIOR_BROKER_EMAILS", "").strip()
    IAP_AUDIENCE: str = os.getenv("IAP_AUDIENCE", "").strip()

    # Herkese açık demo yüzeyinde maliyet/kaynak tüketimini sınırla.
    PUBLIC_DEMO_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("PUBLIC_DEMO_RATE_LIMIT_PER_MINUTE", "10"))
    PUBLIC_DEMO_UPLOAD_LIMIT_PER_MINUTE: int = int(os.getenv("PUBLIC_DEMO_UPLOAD_LIMIT_PER_MINUTE", "5"))
    MAX_BATCH_ITEMS: int = int(os.getenv("MAX_BATCH_ITEMS", "10"))
    BATCH_CONCURRENCY: int = int(os.getenv("BATCH_CONCURRENCY", "4"))

    # GCP Configurations - us-central1 (Iowa) ve gumruk-mevzuat Standartlaştırması
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "gumruk-mevzuat")
    GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")  # us-central1 primary Vertex AI region
    VERTEX_AI_LOCATION: str = os.getenv("VERTEX_AI_LOCATION", "us-central1")
    AUDIT_BACKEND: str = os.getenv("AUDIT_BACKEND", "cloudsql")
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "gumruk-mevzuat-storage-us-central1")
    CLOUD_SQL_CONNECTION_NAME: str = os.getenv("CLOUD_SQL_CONNECTION_NAME", "gumruk-mevzuat:us-central1:gumruk-db")
    INSTANCE_CONNECTION_NAME: str = os.getenv("INSTANCE_CONNECTION_NAME", "gumruk-mevzuat:us-central1:gumruk-db")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASS: str = os.getenv("DB_PASS", "")
    DB_NAME: str = os.getenv("DB_NAME", "gtip_db")

    # Vertex AI Model Mimarisi ve Rol Dağılımı (gcp_architecture_report.md)
    PRIMARY_AI_MODEL: str = os.getenv("PRIMARY_AI_MODEL", "gemini-2.5-flash")
    BULK_EXTRACTOR_MODEL: str = os.getenv("BULK_EXTRACTOR_MODEL", "gemini-2.5-flash-lite")
    DEFAULT_LLM_MODEL: str = os.getenv("DEFAULT_LLM_MODEL", "gemini-2.5-flash")
    FAST_LLM_MODEL: str = os.getenv("FAST_LLM_MODEL", "gemini-2.5-flash-lite")
    EXTRACTOR_LLM_MODEL: str = os.getenv("EXTRACTOR_LLM_MODEL", "gemini-2.5-flash-lite")
    REASONING_LLM_MODEL: str = os.getenv("REASONING_LLM_MODEL", "gemini-2.5-flash")
    AUDITOR_LLM_MODEL: str = os.getenv("AUDITOR_LLM_MODEL", "gemini-2.5-flash")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-005")
    EBTI_EMBEDDING_MODEL: str = os.getenv("EBTI_EMBEDDING_MODEL", "text-multilingual-embedding-002")
    VECTOR_DIM: int = 768

    # Gemini Flash Thinking Parametreleri
    THINKING_BUDGET_EXTRACTOR: int = 0      # Ultra hızlı özellik çıkarımı
    # Kapalı-küme dışlama ve predikat görevleri için ayrı bütçeler. Önceki tek
    # 2048 bütçe, birkaç boolean koşulda gereksiz gecikme yaratıyordu.
    THINKING_BUDGET_EXCLUSION: int = int(os.getenv("THINKING_BUDGET_EXCLUSION", "384"))
    THINKING_BUDGET_VERIFIER: int = int(os.getenv("THINKING_BUDGET_VERIFIER", "1024"))
    # Fasıl seçimi 97 seçenekli ~11 bin token'lık bir yönlendirmedir. Düşünme
    # bütçesi 0 iken model "ahşap sandalye"yi mobilya yerine ahşap eşya faslına
    # gönderiyordu (yüzeysel malzeme eşleşmesi). 12 ürünlük işlev/malzeme
    # denemesinde: bütçe 0 -> 9/12, 256 -> 11/12, 512 -> 12/12 (medyan ~5 sn).
    # Yalnız CHAPTER seviyesinin ilk denemesine uygulanır.
    THINKING_BUDGET_CHAPTER: int = int(os.getenv("THINKING_BUDGET_CHAPTER", "512"))

    # Context cache hazırlığı büyük TGTC bağlamını Vertex'e yüklediği için kullanıcı
    # isteğinin sıcak yolunda çalıştırılmaz. Cache gerekiyorsa ayrı bir bakım işiyle
    # önceden hazırlanmalıdır.
    USE_CONTEXT_CACHE: bool = os.getenv("USE_CONTEXT_CACHE", "false").lower() == "true"
    LLM_TIMEOUT_MS: int = int(os.getenv("LLM_TIMEOUT_MS", "15000"))
    EMBEDDING_TIMEOUT_MS: int = int(os.getenv("EMBEDDING_TIMEOUT_MS", "7000"))
    # Google Search Grounding ile canlı emsal taraması, kapalı-küme seçiminden
    # belirgin biçimde yavaştır. Tek bir LLM_TIMEOUT_MS bütçesi paylaşıldığında
    # üretimde sürekli 504 DEADLINE_EXCEEDED alınıyordu.

    # Hattın TOPLAM süre bütçesi. Tek tek çağrıların timeout'u vardı ama hattın
    # bütünü için sınır yoktu: bir sağlayıcı hatası (429/504) retry'larla
    # çarpılıp dört seviyeye yayılınca analiz 91 saniyeye kadar çıkabiliyordu.
    # Bütçe dolduğunda hat zarifçe durur ve elindeki en iyi sonucu döndürür;
    # cevapsız bir timeout yerine cevaplanabilir bir soru daha değerlidir.
    # 32 sn idi; ürün profili, fasıl dışlama ve fasıl uygunluk kontrolleri
    # eklenince canlıda analizler bütçeye takılıp manuel incelemeye düştü.
    ANALYSIS_BUDGET_MS: int = int(os.getenv("ANALYSIS_BUDGET_MS", "50000"))
    # Arayüzün istek timeout'u 75 sn; güvenlik payı düşülmüş toplam sınır
    # (profil adımı + dolaşım + uluslararası arama). nginx ve Cloud Run
    # sınırları 300 sn olduğundan asıl sınır arayüzdür.
    CLIENT_REQUEST_BUDGET_MS: int = int(os.getenv("CLIENT_REQUEST_BUDGET_MS", "65000"))
    # CHAPTER seçenek listesi hattın en yavaş ve 504 alan çağrısıydı (~21.000
    # token). Kapsam LİSTESİNİ kesmek yanlış çözümdü: Fasıl 61'de 6109 (tişört)
    # gibi yaygın pozisyonlar listeden düşüyordu. Bunun yerine pozisyon
    # ETİKETLERİ kısaltılır; her pozisyon görünür kalır, prompt yarıya iner.
    # 55 -> 20 karakter: ~21.000 -> ~11.300 token.
    CHAPTER_HEADING_LABEL_CHARS: int = int(os.getenv("CHAPTER_HEADING_LABEL_CHARS", "20"))
    # Tek bir faslın kapsamı için üst sınır (Fasıl 84'te 84 pozisyon var).
    CHAPTER_SCOPE_CHARS: int = int(os.getenv("CHAPTER_SCOPE_CHARS", "2600"))
    # Sağlayıcı hatalarında (429 kota, 504 deadline) bekleme. 0.35 sn kotanın
    # yenilenmesi için anlamsızdı; üstel artış uygulanır.
    PROVIDER_RETRY_BASE_MS: int = int(os.getenv("PROVIDER_RETRY_BASE_MS", "1200"))

    # Cloud Run Secret Manager bağlantıları bu değerleri environment'a enjekte eder.
    # Import sırasında Secret Manager çağrısı yapmak cold-start'ı ve hata yüzeyini büyütür.
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # Production backend için deploy betiği bu değeri Secret Manager'dan enjekte eder.
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-only-change-before-production-2026")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 saat

    # CORS — production'da virgülle ayrılmış domain listesi
    CORS_ALLOWED_ORIGINS: str = os.getenv("CORS_ALLOWED_ORIGINS", "")

    # Seçim promptuna hangi kanıtın gireceğini denetleyen ablasyon bayrakları.
    # İkisi birden: (1) benchmark'ta her maddenin doğruluk katkısını tek tek
    # ölçmeyi sağlar — hepsi kapalıyken alınan ölçüm baseline'dır; (2) üretimde
    # bir madde doğruluğu düşürürse yeniden deploy etmeden kapatma imkânı verir.
    SELECTION_USE_RAW_TEXT: bool = os.getenv("SELECTION_USE_RAW_TEXT", "true").lower() == "true"
    SELECTION_USE_PRECEDENTS: bool = os.getenv("SELECTION_USE_PRECEDENTS", "true").lower() == "true"
    SELECTION_USE_CHAPTER_NOTES: bool = os.getenv("SELECTION_USE_CHAPTER_NOTES", "true").lower() == "true"

    # Emsal güdümlü pozisyon yönlendirmesi. Güçlü bir BTB emsali varsa dolaşım
    # 97 fasıllık CHAPTER seçimini atlayıp emsallerin işaret ettiği en çok 3
    # pozisyondan başlar; model bunlarda eşleşme bulamazsa tam dolaşıma dönülür.
    # Eşik 120 numunelik yönlendirme deneyiyle seçildi
    # (scripts/evaluate_heading_routing.py, routing-20260925T101052Z):
    #
    #   eşik  kapıyı geçen  doğru pozisyon ilk 3'te
    #   0.6       %29.2          %91.4
    #   0.8       %23.3          %96.4   <-- seçilen
    #   0.9       %17.5          %100
    #
    # Aramayla fasıl adımını TAMAMEN atlamak ölçümde reddedildi: en iyi füzyon
    # bile doğru pozisyonu numunelerin %41'inde ilk 3'ün dışında bıraktı.
    # Sınıflandırmadan önce ürün profili: eşya ne, ne işe yarar, neyden yapılmış;
    # her bilgi kaynağıyla (beyan / doküman / fotoğraf / sayfa / varsayım).
    # Kararı etkileyen bilgi yalnız varsayımsa kullanıcıya tek soru sorulur.
    # Müşavir geri bildirimi: "cam balkon sistemi" yazılınca alüminyumdan hiç
    # bahsedilmiyordu; kullanıcı malzemeyi yazmamıştı ve model sormuyordu.
    PRODUCT_PROFILE_ENABLED: bool = os.getenv("PRODUCT_PROFILE_ENABLED", "true").lower() == "true"
    PROFILE_CONFIRMATION_ENABLED: bool = os.getenv("PROFILE_CONFIRMATION_ENABLED", "true").lower() == "true"
    PROFILE_LLM_MODEL: str = os.getenv("PROFILE_LLM_MODEL", "gemini-2.5-flash")
    PROFILE_TIMEOUT_MS: int = int(os.getenv("PROFILE_TIMEOUT_MS", "12000"))

    # Bölüm + fasıl notları için prompt bütçesi (karakter). Uzun notlar madde
    # bazında kısaltılır: önce dışlama hükümleri, sonra tanımlar.
    NOTES_BUDGET_CHARS: int = int(os.getenv("NOTES_BUDGET_CHARS", "9000"))
    # Fasıl seçildikten sonra, faslın ve bölümünün dışlama hükümlerine karşı
    # kısa bir kontrol. Fasıl seçimi notsuz yapıldığı için yanlış fasıl ancak
    # pozisyon seviyesinde anlaşılıyor ve bir tur kaybediliyordu.
    CHAPTER_EXCLUSION_CHECK_ENABLED: bool = os.getenv("CHAPTER_EXCLUSION_CHECK_ENABLED", "true").lower() == "true"
    # Model kendi seçtiği ilk fasılda pozisyon sorusu sormak isterse, soru
    # müşaviriye gösterilmeden önce faslın ürüne uyup uymadığı sorgulanır.
    # Cam balkon Fasıl 70'te "float mı, temperli mi?" sorusuna takılıyordu.
    CHAPTER_FIT_CHECK_ENABLED: bool = os.getenv("CHAPTER_FIT_CHECK_ENABLED", "true").lower() == "true"

    HEADING_ROUTING_ENABLED: bool = os.getenv("HEADING_ROUTING_ENABLED", "true").lower() == "true"
    HEADING_ROUTING_MIN_BTB: float = float(os.getenv("HEADING_ROUTING_MIN_BTB", "0.80"))
    HEADING_ROUTING_MAX_HEADINGS: int = int(os.getenv("HEADING_ROUTING_MAX_HEADINGS", "3"))

    # RAG & Decision Settings
    # BTB'ler retrieval/reranking için değerli emsallerdir; ancak üçüncü kişiler
    # bakımından normatif bir kaynak değildir. Bu yüzden nihai aday skoruna ağırlık
    # olarak katılmazlar. Yasal notlar/GYK ayrı deterministic kapıda uygulanır.
    BTB_WEIGHT: float = 0.0
    TGTC_WEIGHT: float = 1.0
    # Eşik 86 numunelik etiketli ölçümle seçildi (scripts/calibrate_confidence.py).
    # Kalibre edilmiş skorla eşik taraması:
    #
    #   eşik  işaretlenen  yakalanan yanlış  boşuna işaret
    #   0.45           20            15/44               5
    #   0.50           61            41/44              20   <-- seçilen
    #   0.55           62            42/44              20
    #   0.70           72            43/44              29
    #
    # 0.50'de yanlış kararların %93'ü yakalanıyor. Bedeli 20 doğru kararın da
    # incelemeye gitmesi; sistemin yaprak doğruluğu %49 olduğu sürece bu dürüst
    # bir orandır. İşaret engelleyici değildir: kod ve dayanak yine gösterilir.
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.50"))
    RRF_K: int = 60

settings = Settings()

# Güvenlik uyarıları
if settings.ENVIRONMENT == "production":
    if not settings.GEMINI_API_KEY:
        logger.info("[Vertex AI] GEMINI_API_KEY tanımlı değil; sistem Cloud Run Service Account (ADC) ve Vertex AI IAM yetkileri ile çalışıyor.")
    if not os.getenv("CLOUD_RUN_JOB") and (
        not settings.JWT_SECRET_KEY or "dev-only" in settings.JWT_SECRET_KEY
    ):
        raise RuntimeError("Production backend için JWT_SECRET_KEY zorunludur.")
    if settings.CORS_ALLOWED_ORIGINS == "*":
        raise RuntimeError("Production ortamında CORS_ALLOWED_ORIGINS='*' kullanılamaz.")
