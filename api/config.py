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
    VECTOR_DIM: int = 768

    # Gemini Flash Thinking Parametreleri
    THINKING_BUDGET_EXTRACTOR: int = 0      # Ultra hızlı özellik çıkarımı
    # Kapalı-küme dışlama ve predikat görevleri için ayrı bütçeler. Önceki tek
    # 2048 bütçe, birkaç boolean koşulda gereksiz gecikme yaratıyordu.
    THINKING_BUDGET_EXCLUSION: int = int(os.getenv("THINKING_BUDGET_EXCLUSION", "384"))
    THINKING_BUDGET_VERIFIER: int = int(os.getenv("THINKING_BUDGET_VERIFIER", "1024"))

    # Context cache hazırlığı büyük TGTC bağlamını Vertex'e yüklediği için kullanıcı
    # isteğinin sıcak yolunda çalıştırılmaz. Cache gerekiyorsa ayrı bir bakım işiyle
    # önceden hazırlanmalıdır.
    USE_CONTEXT_CACHE: bool = os.getenv("USE_CONTEXT_CACHE", "false").lower() == "true"
    LLM_TIMEOUT_MS: int = int(os.getenv("LLM_TIMEOUT_MS", "15000"))
    EMBEDDING_TIMEOUT_MS: int = int(os.getenv("EMBEDDING_TIMEOUT_MS", "7000"))

    # Cloud Run Secret Manager bağlantıları bu değerleri environment'a enjekte eder.
    # Import sırasında Secret Manager çağrısı yapmak cold-start'ı ve hata yüzeyini büyütür.
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # Production backend için deploy betiği bu değeri Secret Manager'dan enjekte eder.
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-only-change-before-production-2026")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 saat

    # CORS — production'da virgülle ayrılmış domain listesi
    CORS_ALLOWED_ORIGINS: str = os.getenv("CORS_ALLOWED_ORIGINS", "")

    # RAG & Decision Settings
    # BTB'ler retrieval/reranking için değerli emsallerdir; ancak üçüncü kişiler
    # bakımından normatif bir kaynak değildir. Bu yüzden nihai aday skoruna ağırlık
    # olarak katılmazlar. Yasal notlar/GYK ayrı deterministic kapıda uygulanır.
    BTB_WEIGHT: float = 0.0
    TGTC_WEIGHT: float = 1.0
    CONFIDENCE_THRESHOLD: float = 0.90
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
