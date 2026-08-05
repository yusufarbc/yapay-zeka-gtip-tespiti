"""
GCP Cloud SQL (PostgreSQL) SQLAlchemy 2.0 ORM Veritabanı Modülü.
Tüm FastAPI uç noktaları ve durum depoları için tekil (Singleton)
ORM Engine, SessionLocal ve Dependency get_db() sağlar.
"""
import os
import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

from sqlalchemy import Column, String, Float, Boolean, Text, DateTime, func

# SQLAlchemy Declarative Base Model
Base = declarative_base()

class AuditLogModel(Base):
    """SQLAlchemy ORM Model for Audit Logs stored in GCP Cloud SQL PostgreSQL."""
    __tablename__ = "audit_logs"

    session_id = Column(String(255), primary_key=True)
    timestamp = Column(String(100), nullable=True)
    user_email = Column(String(255), nullable=True)
    user_role = Column(String(100), nullable=True)
    product_name = Column(Text, nullable=True)
    initial_gtip_proposed = Column(String(50), nullable=True)
    final_gtip_approved = Column(String(50), nullable=True)
    confidence_score = Column(Float, nullable=True)
    is_hitl_triggered = Column(Boolean, default=False)
    user_feedback = Column(Text, nullable=True)
    execution_time_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

def get_database_url() -> str:
    """GCP Cloud SQL PostgreSQL bağlantı dizesini döndürür."""
    cloud_sql_conn = os.getenv("CLOUD_SQL_CONNECTION_NAME", "gtip-tespit-projesi:europe-west3:gtip-db")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASS", "")
    db_name = os.getenv("DB_NAME", "gtip_db")

    if os.getenv("ENVIRONMENT") == "production" or os.getenv("CLOUD_SQL_CONNECTION_NAME"):
        # GCP Cloud Run Cloud SQL Auth Proxy Unix Socket bağlantısı
        return f"postgresql+psycopg2://{db_user}:{db_pass}@/{db_name}?host=/cloudsql/{cloud_sql_conn}"
    else:
        # Geliştirme / Test ortamı fallback
        import tempfile
        db_file = os.path.join(tempfile.gettempdir(), "gtip_app_runtime_data", "cloud_sql_fallback.db")
        os.makedirs(os.path.dirname(db_file), exist_ok=True)
        return f"sqlite:///{db_file}"

DATABASE_URL = get_database_url()

# SQLAlchemy 2.0 Engine ve Session Factory
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_orm_tables():
    """GCP Cloud SQL PostgreSQL veritabanı tablolarını oluşturur."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("[SQLAlchemy ORM] GCP Cloud SQL PostgreSQL tabloları başarıyla doğrulandı.")
    except Exception as e:
        logger.warning(f"[SQLAlchemy ORM] Tablo oluşturma uyarısı: {e}")

def get_db() -> Generator[Session, None, None]:
    """FastAPI uç noktaları için SQLAlchemy DB Session Dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
