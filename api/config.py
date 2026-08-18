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
        project_id = os.getenv("GCP_PROJECT_ID", "gtip-tespit-projesi")
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
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    USE_GCP_EMULATOR: bool = os.getenv("USE_GCP_EMULATOR", "false").lower() == "true"
    ALLOW_PUBLIC_DEMO_ACCESS: bool = os.getenv("ALLOW_PUBLIC_DEMO_ACCESS", "true").lower() == "true"

    # GCP Configurations
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "gtip-tespit-projesi")
    GCP_REGION: str = os.getenv("GCP_REGION", "europe-west3")  # Frankfurt primary low-latency region
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "gtip-evrak-bucket-gtip-tespit-projesi")
    CLOUD_SQL_CONNECTION_NAME: str = os.getenv("CLOUD_SQL_CONNECTION_NAME", "gtip-tespit-projesi:europe-west3:gtip-db")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASS: str = os.getenv("DB_PASS", "")
    DB_NAME: str = os.getenv("DB_NAME", "gtip_db")

    # AI Models
    DEFAULT_LLM_MODEL: str = os.getenv("DEFAULT_LLM_MODEL", "gemini-3.6-flash")
    EXTRACTOR_LLM_MODEL: str = os.getenv("EXTRACTOR_LLM_MODEL", "gemini-3.6-flash")
    REASONING_LLM_MODEL: str = os.getenv("REASONING_LLM_MODEL", "gemini-3.6-flash")
    AUDITOR_LLM_MODEL: str = os.getenv("AUDITOR_LLM_MODEL", "gemini-3.6-flash")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-005")

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
    # Örnek: "https://gtip.sirketiniz.com,https://app.sirketiniz.com"
    CORS_ALLOWED_ORIGINS: str = os.getenv("CORS_ALLOWED_ORIGINS", "*")

    # RAG & Decision Settings
    BTB_WEIGHT: float = 0.70
    TGTC_WEIGHT: float = 0.30
    CONFIDENCE_THRESHOLD: float = 0.90

settings = Settings()

# Güvenlik uyarıları
if settings.ENVIRONMENT == "production":
    if not settings.GEMINI_API_KEY:
        logger.error("[GÜVENLİK] GEMINI_API_KEY production ortamında boş! Secret Manager kontrolü yapın.")
    if "dev-only" in settings.JWT_SECRET_KEY:
        logger.error("[GÜVENLİK] JWT_SECRET_KEY production için geçersiz! Secret Manager'da 'gtip-jwt-secret' secret'ı tanımlayın.")
    if settings.CORS_ALLOWED_ORIGINS == "*":
        logger.warning("[GÜVENLİK] CORS_ALLOWED_ORIGINS production'da '*' olarak bırakılmış. CORS_ALLOWED_ORIGINS env var'ını ayarlayın.")
