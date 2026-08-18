"""
GCP Cloud SQL (PostgreSQL) SQLAlchemy 2.0 ORM Veritabanı Modülü.
Tüm FastAPI uç noktaları ve durum depoları için tekil (Singleton)
ORM Engine, SessionLocal ve Dependency get_db() sağlar.
"""
import os
import json
import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, func, text, UniqueConstraint

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

class GumrukSiniflandirmaKarariModel(Base):
    """
    SQLAlchemy ORM Model for Resmi Gazete Sınıflandırma Kararları.
    Harfi harfine (exact-match) halüsinasyonsuz süzülen orijinal mevzuat metinlerini saklar.
    """
    __tablename__ = "gumruk_siniflandirma_kararlari"
    __table_args__ = (
        UniqueConstraint('gtip_kodu', 'yayin_tarihi', name='uq_siniflandirma_gtip_yayin'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    karar_tipi = Column(String(50), default="SINIFLANDIRMA_KARARI", index=True, nullable=False)
    gtip_kodu = Column(String(20), index=True, nullable=False)
    yayin_tarihi = Column(String(30), nullable=False)
    resmi_gazete_sayisi = Column(String(50), nullable=True)
    esya_tanimi = Column(Text, nullable=True)
    hukuki_gerekce = Column(Text, nullable=False)  # Birebir kopyalanan orijinal metin
    kaynak_url = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class GumrukEmsalKararModel(Base):
    """
    SQLAlchemy ORM Model for Unified Customs Decisions (BTB & Sınıflandırma Kararları).
    T.C. Resmi Gazete ve AB EBTI kararlarını ortak şemada tutar, Vektör RAG engine ve SQL sorguları için optimize edilir.
    """
    __tablename__ = "gumruk_emsal_kararlar"

    id = Column(Integer, primary_key=True, autoincrement=True)
    karar_tipi = Column(String(30), index=True, nullable=False)  # 'BTB' veya 'SINIFLANDIRMA_KARARI'
    referans_no = Column(String(100), nullable=True)             # Tebliğ Sıra No veya BTB Numarası
    yayin_tarihi = Column(String(30), nullable=True)
    resmi_gazete_sayisi = Column(String(50), nullable=True)      # Örn: 33121 veya 33121 Mükerrer
    gtip_kodu = Column(String(20), index=True, nullable=False)   # 8 veya 12 haneli GTİP kodu
    esya_tanimi = Column(Text, nullable=False)
    hukuki_gerekce = Column(Text, nullable=True)
    kaynak_url = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    valid_until = Column(String(30), nullable=True, default="9999-12-31")  # Mevzuat versiyonlama

class TgtcRuleModel(Base):
    """SQLAlchemy ORM Model for TGTC Yorum Kuralları and Ölçü Birimleri."""
    __tablename__ = "tgtc_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_type = Column(String(50), nullable=False)  # 'GIR' or 'MEASUREMENT'
    rule_number = Column(String(10), nullable=True) # e.g., '1', '2(a)'
    title = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)

class TgtcNoteModel(Base):
    """SQLAlchemy ORM Model for TGTC Fasıl Notları and İzahnameler."""
    __tablename__ = "tgtc_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_code = Column(String(10), index=True, nullable=False) # e.g., '01', '97'
    text = Column(Text, nullable=False)

class TgtcGtipModel(Base):
    """SQLAlchemy ORM Model for TGTC Tree (Fasıl, Pozisyon, Alt Pozisyon, GTİP)."""
    __tablename__ = "tgtc_gtip"

    gtip_code = Column(String(20), primary_key=True) # e.g., '01', '0101', '010121000000'
    level = Column(String(10), index=True, nullable=False) # 'CHAPTER', 'HEADING', 'GTIP'
    parent_code = Column(String(20), index=True, nullable=True)
    description = Column(Text, nullable=False)
    tax_rate = Column(String(50), nullable=True)
    unit = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)

def get_database_url() -> str:
    """GCP Cloud SQL PostgreSQL bağlantı dizesini döndürür."""
    # Öncelikli: Tanımlanmış tam DATABASE_URL varsa doğrudan kullan (TCP IP, Custom Socket vs.)
    env_db_url = os.getenv("DATABASE_URL")
    if env_db_url and env_db_url.strip():
        return env_db_url.strip()

    cloud_sql_conn = os.getenv("CLOUD_SQL_CONNECTION_NAME", "gtip-tespit-projesi:europe-west3:gtip-db")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASS", "")
    db_name = os.getenv("DB_NAME", "gtip_db")

    if os.getenv("ENVIRONMENT") == "production" or os.getenv("CLOUD_SQL_CONNECTION_NAME"):
        # GCP Cloud Run Cloud SQL Auth Proxy Unix Socket bağlantısı (Fallback)
        return f"postgresql+psycopg2://{db_user}:{db_pass}@/{db_name}?host=/cloudsql/{cloud_sql_conn}"
    else:
        # Geliştirme / Test ortamı fallback
        import tempfile
        db_file = os.path.join(tempfile.gettempdir(), "gtip_app_runtime_data", "cloud_sql_fallback.db")
        os.makedirs(os.path.dirname(db_file), exist_ok=True)
        return f"sqlite:///{db_file}"

DATABASE_URL = get_database_url()

# SQLAlchemy 2.0 Engine ve Session Factory
connect_args = {"connect_timeout": 5} if DATABASE_URL.startswith("postgresql") else {}
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=2,        # Cloud Run instance başına düşük pool size (serverless optimization)
    max_overflow=3,     # Yoğun yükte max +3 connection
    pool_recycle=600,   # Cloud SQL connection reuse lifetime (10 dakika - idle connection drop önlemi)
    pool_timeout=30,    # Max wait time for a connection
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_orm_tables():
    """GCP Cloud SQL PostgreSQL veritabanı tablolarını güvenli olarak oluşturur ve eski sahte verileri temizler."""
    try:
        Base.metadata.create_all(bind=engine)
        # 🚨 OTOMATİK MOCK VERİ TEMİZLEYİCİ (Zero-Hallucination Koruması) 🚨
        try:
            with SessionLocal() as session:
                d2 = session.query(GumrukEmsalKararModel).filter(
                    GumrukEmsalKararModel.referans_no.like("Gumruk Genel Tebligi%") | 
                    GumrukEmsalKararModel.referans_no.like("Teblig Takip%") |
                    GumrukEmsalKararModel.referans_no.like("TR-BTB-%")
                ).delete(synchronize_session=False)

                d3 = session.query(GumrukSiniflandirmaKarariModel).filter(
                    GumrukSiniflandirmaKarariModel.resmi_gazete_sayisi.like("%Mükerrer%") & 
                    GumrukSiniflandirmaKarariModel.kaynak_url.like("https://www.resmigazete.gov.tr")
                ).delete(synchronize_session=False)

                session.commit()
                if (d2 or 0) > 0 or (d3 or 0) > 0:
                    logger.info(f"[SQLAlchemy ORM] {(d2 or 0) + (d3 or 0)} adet tohum/sahte karar Cloud SQL'den kalıcı olarak SİLİNDİ!")
        except Exception as ex_mock:
            logger.warning(f"[SQLAlchemy ORM] Mock silme uyarısı: {ex_mock}")

        # 🚀 OTOMATİK CLOUD SQL TOHUMLAYICI (2026 TGTC Tarife Ağacı) 🚀
        try:
            with SessionLocal() as session:
                from api.db.database import TgtcGtipModel
                count_gtip = session.query(TgtcGtipModel).count()
                if count_gtip == 0:
                    logger.info("[SQLAlchemy ORM] Cloud SQL Tarife Ağacı boş! '2026 TGTC' dizininden 01-99 Fashiıllar ve GTİP tohumlaması başlatılıyor...")
                    from scripts.populate_tgtc_cloudsql import extract_gir_rules, extract_chapter_notes, populate_gtip_tree
                    extract_gir_rules(session)
                    extract_chapter_notes(session)
                    populate_gtip_tree(session)
                    logger.info("[SQLAlchemy ORM] 2026 TGTC Tarife Ağacı (01-99 Fasıllar) başarıyla Cloud SQL'e yüklendi!")
                else:
                    logger.info(f"[SQLAlchemy ORM] 2026 TGTC Tarife Ağacı mevcut ({count_gtip} kayıt aktif).")
        except Exception as ex_seed:
            logger.warning(f"[SQLAlchemy ORM] TGTC Tohumlama uyarısı: {ex_seed}")
            
        logger.info("[SQLAlchemy ORM] GCP Cloud SQL PostgreSQL tabloları başarıyla doğrulandı ve güncellendi.")
    except Exception as e:
        logger.warning(f"[SQLAlchemy ORM] Tablo oluşturma uyarısı (Non-blocking): {e}")

def get_db() -> Generator[Session, None, None]:
    """FastAPI uç noktaları için SQLAlchemy DB Session Dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
