import os
import logging

logger = logging.getLogger(__name__)

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseModel as BaseSettings

def _get_secret(secret_id: str, fallback: str = "") -> str:
    """
    GCP Secret Manager'dan secret değerini çeker.
    Production ortamında Secret Manager kullanılır;
    geliştirme ortamında environment variable fallback uygulanır.
    """
    try:
        from google.cloud import secretmanager
        project_id = os.getenv("GCP_PROJECT_ID", "gumruk-mevzuat")
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        value = response.payload.data.decode("UTF-8").strip()
        logger.info(f"[Secret Manager] '{secret_id}' başarıyla okundu.")
        return value
    except Exception:
        # Geliştirme ortamında veya Secret Manager erişimi yoksa env var kullan
        return fallback

class Settings(BaseSettings):
    PROJECT_NAME: str = "GTİP Tespit ve Karar Destek Sistemi API"
    VERSION: str = "1.1.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    USE_GCP_EMULATOR: bool = os.getenv("USE_GCP_EMULATOR", "false").lower() == "true"
    ALLOW_PUBLIC_DEMO_ACCESS: bool = os.getenv("ALLOW_PUBLIC_DEMO_ACCESS", "true").lower() == "true"

    # GCP Configurations - us-central1 (Iowa) ve gumruk-mevzuat Standartlaştırması
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "gumruk-mevzuat")
    GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")  # us-central1 primary Vertex AI region
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
    REASONING_LLM_MODEL: str = os.getenv("REASONING_LLM_MODEL", "gemini-2.5-pro")
    AUDITOR_LLM_MODEL: str = os.getenv("AUDITOR_LLM_MODEL", "gemini-2.5-pro")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-005")
    VECTOR_DIM: int = 768

    # Gemini Flash Thinking Parametreleri
    THINKING_BUDGET_EXTRACTOR: int = 0      # Ultra hızlı özellik çıkarımı
    THINKING_BUDGET_VERIFIER: int = 2048   # Derin yasal gerekçelendirme ve dışlama analizi

    USE_CONTEXT_CACHE: bool = os.getenv("USE_CONTEXT_CACHE", "true").lower() == "true"

    # AI API Key — Secret Manager > env var > boş
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "") or _get_secret(
        "gtip-gemini-api-key", fallback=os.getenv("GEMINI_API_KEY", "")
    )

    # Security & Auth — Secret Manager > env var > geliştirme fallback
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "") or _get_secret(
        "gtip-jwt-secret",
        fallback=os.getenv("JWT_SECRET_KEY", "dev-only-change-before-production-2026")
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 saat

    # CORS — production'da virgülle ayrılmış domain listesi
    CORS_ALLOWED_ORIGINS: str = os.getenv("CORS_ALLOWED_ORIGINS", "*")

    # RAG & Decision Settings
    BTB_WEIGHT: float = 0.70
    TGTC_WEIGHT: float = 0.30
    CONFIDENCE_THRESHOLD: float = 0.90
    RRF_K: int = 60

settings = Settings()

# Güvenlik uyarıları
if settings.ENVIRONMENT == "production":
    if not settings.GEMINI_API_KEY:
        logger.info("[Vertex AI] GEMINI_API_KEY tanımlı değil; sistem Cloud Run Service Account (ADC) ve Vertex AI IAM yetkileri ile çalışıyor.")
    if "dev-only" in settings.JWT_SECRET_KEY:
        logger.warning("[GÜVENLİK] JWT_SECRET_KEY varsayılan değerde. Secret Manager'da 'gtip-jwt-secret' secret'ı tanımlanabilir.")
    if settings.CORS_ALLOWED_ORIGINS == "*":
        logger.warning("[GÜVENLİK] CORS_ALLOWED_ORIGINS production'da '*' olarak bırakılmış. CORS_ALLOWED_ORIGINS env var'ını ayarlayın.")
