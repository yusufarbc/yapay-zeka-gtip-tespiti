import os

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseModel as BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "GTİP Tespit ve Karar Destek Sistemi API"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    USE_GCP_EMULATOR: bool = os.getenv("USE_GCP_EMULATOR", "true").lower() == "true"
    
    # GCP Configurations
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "gtip-tespit-projesi")
    GCP_REGION: str = os.getenv("GCP_REGION", "europe-west3") # Frankfurt primary low-latency region
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "gtip-evrak-bucket-gtip-tespit-projesi")
    
    # AI Models
    DEFAULT_LLM_MODEL: str = os.getenv("DEFAULT_LLM_MODEL", "gemini-3.6-flash")
    EXTRACTOR_LLM_MODEL: str = os.getenv("EXTRACTOR_LLM_MODEL", "gemini-3.6-flash-lite")
    REASONING_LLM_MODEL: str = os.getenv("REASONING_LLM_MODEL", "gemini-3.6-flash")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-005")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # Security & Auth
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "super-secret-gtip-key-change-in-prod-2026")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 24 hours
    
    # RAG & Decision Settings
    BTB_WEIGHT: float = 0.70
    TGTC_WEIGHT: float = 0.30
    CONFIDENCE_THRESHOLD: float = 0.90

settings = Settings()
