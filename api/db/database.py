"""
GCP Cloud SQL (PostgreSQL + pgvector) SQLAlchemy 2.0 ORM Veritabanı Modülü.
Tüm FastAPI uç noktaları, Hiyerarşik Hibrit RAG motoru ve durum depoları için
tekil (Singleton) ORM Engine, SessionLocal, Dependency get_db() ve
vektör/metin hibrit arama fonksiyonları sağlar.
"""
import os
import uuid
import json
import logging
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Generator, List, Dict, Any, Optional, Tuple
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    Text, DateTime, func, text, UniqueConstraint, Index, or_
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.engine import URL
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_subheading_contexts() -> Dict[str, Dict[str, Any]]:
    """Ham cetvelde düşen ara grup başlıklarını veri katmanından yükler."""
    path = Path(__file__).resolve().parents[1] / "data" / "tgtc_subheading_context.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            re.sub(r"\D", "", str(code)): value
            for code, value in payload.get("subheadings", {}).items()
            if isinstance(value, dict)
        }
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Alt pozisyon bağlam verisi yüklenemedi: %s", exc)
        return {}

# pgvector SQLAlchemy eklenti kontrolü
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

class VectorType(TypeDecorator):
    """
    Platform-bağımsız 768 boyutlu Vektör tipi.
    PostgreSQL ortamında native pgvector 'Vector(768)' kullanır;
    SQLite / local test fallback durumunda JSON text olarak saklar.
    """
    impl = Text
    cache_ok = True

    def __init__(self, dim: int = 768, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and Vector is not None:
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql" and Vector is not None:
            return value
        if isinstance(value, (list, tuple)):
            return json.dumps(list(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

# SQLAlchemy Declarative Base Model
Base = declarative_base()

class AuditLogModel(Base):
    """SQLAlchemy ORM Model for Audit Logs stored in GCP Cloud SQL PostgreSQL."""
    __tablename__ = "audit_logs"

    session_id = Column(String(255), primary_key=True)
    timestamp = Column(String(100), nullable=True)
    user_email = Column(String(255), nullable=True, index=True)
    user_role = Column(String(100), nullable=True)
    product_name = Column(Text, nullable=True)
    initial_gtip_proposed = Column(String(50), nullable=True, index=True)
    final_gtip_approved = Column(String(50), nullable=True, index=True)
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
    __table_args__ = (
        UniqueConstraint("karar_tipi", "referans_no", name="uq_emsal_type_reference"),
        Index("idx_emsal_gtip_valid", "gtip_kodu", "valid_until"),
        Index("idx_emsal_karar_tipi", "karar_tipi"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    karar_tipi = Column(String(30), index=True, nullable=False)  # 'BTB' veya 'SINIFLANDIRMA_KARARI'
    referans_no = Column(String(100), nullable=True, index=True) # Tebliğ Sıra No veya BTB Numarası
    yayin_tarihi = Column(String(30), nullable=True)
    resmi_gazete_sayisi = Column(String(50), nullable=True)      # Örn: 33121 veya 33121 Mükerrer
    gtip_kodu = Column(String(20), index=True, nullable=False)   # 8 veya 12 haneli GTİP kodu
    chapter_code = Column(String(10), index=True, nullable=True) # 2-haneli fasıl
    esya_tanimi = Column(Text, nullable=False)
    hukuki_gerekce = Column(Text, nullable=True)
    kaynak_url = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    valid_until = Column(String(30), nullable=True, default="9999-12-31", index=True)  # Mevzuat versiyonlama
    embedding = Column(VectorType(768), nullable=True)           # 768d text-embedding-005 vektörü

class TgtcRuleModel(Base):
    """SQLAlchemy ORM Model for TGTC Yorum Kuralları and Ölçü Birimleri."""
    __tablename__ = "tgtc_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_type = Column(String(50), index=True, nullable=False)  # 'GIR' or 'MEASUREMENT'
    rule_number = Column(String(10), index=True, nullable=True) # e.g., '1', '2(a)'
    title = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)

class TgtcNoteModel(Base):
    """SQLAlchemy ORM Model for TGTC Fasıl Notları, Dışlama Notları ve İzahnameler."""
    __tablename__ = "tgtc_notes"
    __table_args__ = (
        Index("idx_tgtc_notes_chapter_type", "chapter_code", "note_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_code = Column(String(10), index=True, nullable=False) # e.g., '01', '97'
    note_type = Column(String(50), default="GENERAL", index=True, nullable=False) # 'GENERAL' | 'EXCLUSION' | 'DEFINITIONS'
    title = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)
    embedding = Column(VectorType(768), nullable=True)           # 768d text-embedding-005 vektörü

class TgtcGtipModel(Base):
    """SQLAlchemy ORM Model for TGTC Tree (Fasıl, Pozisyon, Alt Pozisyon, GTİP)."""
    __tablename__ = "tgtc_gtip"
    __table_args__ = (
        Index("idx_tgtc_gtip_chap_level", "chapter_code", "level"),
        Index("idx_tgtc_gtip_parent", "parent_code"),
        Index("idx_tgtc_gtip_active", "is_active"),
    )

    gtip_code = Column(String(20), primary_key=True) # e.g., '01', '0101', '010121000000'
    level = Column(String(10), index=True, nullable=False) # 'CHAPTER', 'HEADING', 'GTIP'
    chapter_code = Column(String(10), index=True, nullable=True) # e.g., '01', '84'
    parent_code = Column(String(20), index=True, nullable=True)
    description = Column(Text, nullable=False)
    tax_rate = Column(String(50), nullable=True)
    unit = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    gecerlilik_baslangic = Column(String(30), nullable=True, default="2026-01-01", index=True)
    gecerlilik_bitis = Column(String(30), nullable=True, index=True)
    kaynak_resmi_gazete_no = Column(String(50), nullable=True)
    embedding = Column(VectorType(768), nullable=True)           # 768d text-embedding-005 vektörü


class TgtcGtipVersionModel(Base):
    """Değişen tarife satırlarının silinmeden saklanan tarihsel sürümü."""
    __tablename__ = "tgtc_gtip_versions"
    __table_args__ = (
        UniqueConstraint("gtip_code", "gecerlilik_baslangic", name="uq_gtip_version_start"),
        Index("idx_gtip_version_validity", "gtip_code", "gecerlilik_bitis"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    gtip_code = Column(String(20), nullable=False, index=True)
    level = Column(String(10), nullable=False)
    chapter_code = Column(String(10), nullable=True)
    parent_code = Column(String(20), nullable=True)
    description = Column(Text, nullable=False)
    tax_rate = Column(String(50), nullable=True)
    unit = Column(String(50), nullable=True)
    gecerlilik_baslangic = Column(String(30), nullable=False)
    gecerlilik_bitis = Column(String(30), nullable=True)
    kaynak_resmi_gazete_no = Column(String(50), nullable=True)

# ==============================================================================
# YENİ GCP ALLOYDB AI / CLOUD SQL ŞARTNAME MODELLERİ (gcp_architecture_report.md)
# ==============================================================================

class GumrukMevzuatMaddesiModel(Base):
    """1. Resmi Gazete Mevzuat Maddeleri Tablosu (Bölüm 4 Şartnamesi)"""
    __tablename__ = "gumruk_mevzuat_maddeleri"
    __table_args__ = (
        Index("idx_mevzuat_lookup", "kanun_no", "madde_kodu"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tarih = Column(String(30), nullable=False, index=True)
    resmi_gazete_sayisi = Column(Integer, nullable=False)
    kanun_no = Column(String(50), nullable=False, index=True)          # Örn: '3065', '4458'
    madde_kodu = Column(String(100), nullable=False)                   # Örn: 'MADDE 15', 'GEÇİCİ MADDE 46'
    madde_metni = Column(Text, nullable=False)                          # Ham resmi gazete metni
    kaynak_url = Column(Text, nullable=False)                           # Doğrudan Resmi Gazete linki
    icerik_vektor = Column(VectorType(768), nullable=True)             # text-embedding-005 boyutu
    created_at = Column(DateTime, server_default=func.now())

class GtipRuleModel(Base):
    """2. Dinamik GTİP Kural Ağacı Tablosu (Bölüm 4 Şartnamesi)"""
    __tablename__ = "gtip_rules"
    __table_args__ = (
        Index("idx_rules_heading", "parent_heading"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_heading = Column(String(10), nullable=False, index=True)     # 4 haneli pozisyon (Örn: '8471')
    target_gtip = Column(String(30), nullable=True)                     # 12 haneli kod (Örn: '8471.30.00.00.11')
    parametre_adi = Column(String(50), nullable=False)                 # 'weight', 'power', 'composition'
    kosul_operatoru = Column(String(10), nullable=False)               # '<=', '>', '==', 'contains'
    esik_deger = Column(String(50), nullable=False)                    # '10kg', '200g/m2'
    soru_metni = Column(Text, nullable=False)                          # Müşavire yöneltilecek soru
    secenekler = Column(Text, nullable=False)                          # Soru şıkları (JSON string)
    oncelik = Column(Integer, default=1)

class EmsalBtbKarariModel(Base):
    """3. Emsal BTB (Bağlayıcı Tarife Bilgisi) Kararları Tablosu (Bölüm 4 Şartnamesi)"""
    __tablename__ = "emsal_btb_kararlari"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    btb_referans_no = Column(String(50), unique=True, nullable=False, index=True) # Örn: 'TR-34-2025-0042'
    gtip_kodu = Column(String(30), nullable=False, index=True)
    urun_tanimi = Column(Text, nullable=False)
    karar_gerekcesi = Column(Text, nullable=False)
    gecerlilik_tarihi = Column(String(30), nullable=False)
    icerik_vektor = Column(VectorType(768), nullable=True)

def get_database_url() -> str:
    """GCP Cloud SQL PostgreSQL bağlantı dizesini döndürür."""
    env_db_url = os.getenv("DATABASE_URL")
    if env_db_url and env_db_url.strip():
        return env_db_url.strip()

    cloud_sql_conn = (
        os.getenv("CLOUD_SQL_CONNECTION_NAME") 
        or os.getenv("INSTANCE_CONNECTION_NAME") 
        or "gumruk-mevzuat:us-central1:gumruk-db"
    )
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASS", "")
    db_name = os.getenv("DB_NAME", "gtip_db")

    if os.getenv("ENVIRONMENT") == "production" or os.getenv("CLOUD_SQL_CONNECTION_NAME"):
        # GCP Cloud Run Cloud SQL Auth Proxy Unix Socket bağlantısı
        return URL.create(
            "postgresql+psycopg2",
            username=db_user,
            password=db_pass,
            database=db_name,
            query={"host": f"/cloudsql/{cloud_sql_conn}"},
        ).render_as_string(hide_password=False)
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
    pool_size=int(os.getenv("DB_POOL_SIZE", "1")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "1")),
    pool_recycle=600,   # Cloud SQL connection reuse lifetime (10 dakika)
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "10")),
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_orm_tables():
    """GCP Cloud SQL PostgreSQL veritabanı tablolarını güvenli olarak oluşturur ve pgvector eklentisini hazırlar."""
    try:
        # 1. PostgreSQL için pgvector eklentisini etkinleştir
        if engine.dialect.name == "postgresql":
            try:
                with engine.connect() as conn:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                    conn.commit()
                    logger.info("[SQLAlchemy ORM] PostgreSQL 'vector' (pgvector) eklentisi doğrulandı/oluşturuldu.")
            except Exception as ex_vec:
                logger.warning(f"[SQLAlchemy ORM] pgvector eklenti uyarısı: {ex_vec}")

        # 2. Tabloları oluştur
        Base.metadata.create_all(bind=engine)

        # 2a. PostgreSQL Şema Otomatik Güncellemesi (Eski tablolara eksik kolonları ekle)
        if engine.dialect.name == "postgresql":
            try:
                with engine.connect() as conn:
                    # tgtc_gtip
                    conn.execute(text("ALTER TABLE tgtc_gtip ADD COLUMN IF NOT EXISTS chapter_code VARCHAR(10);"))
                    conn.execute(text("ALTER TABLE tgtc_gtip ADD COLUMN IF NOT EXISTS embedding vector(768);"))
                    conn.execute(text("ALTER TABLE tgtc_gtip ADD COLUMN IF NOT EXISTS gecerlilik_baslangic VARCHAR(30) DEFAULT '2026-01-01';"))
                    conn.execute(text("ALTER TABLE tgtc_gtip ADD COLUMN IF NOT EXISTS gecerlilik_bitis VARCHAR(30);"))
                    conn.execute(text("ALTER TABLE tgtc_gtip ADD COLUMN IF NOT EXISTS kaynak_resmi_gazete_no VARCHAR(50);"))
                    
                    # tgtc_notes
                    conn.execute(text("ALTER TABLE tgtc_notes ADD COLUMN IF NOT EXISTS note_type VARCHAR(50) DEFAULT 'GENERAL';"))
                    conn.execute(text("ALTER TABLE tgtc_notes ADD COLUMN IF NOT EXISTS title VARCHAR(255);"))
                    conn.execute(text("ALTER TABLE tgtc_notes ADD COLUMN IF NOT EXISTS embedding vector(768);"))
                    
                    # gumruk_emsal_kararlar
                    conn.execute(text("ALTER TABLE gumruk_emsal_kararlar ADD COLUMN IF NOT EXISTS chapter_code VARCHAR(10);"))
                    conn.execute(text("ALTER TABLE gumruk_emsal_kararlar ADD COLUMN IF NOT EXISTS valid_until VARCHAR(20) DEFAULT '9999-12-31';"))
                    conn.execute(text("ALTER TABLE gumruk_emsal_kararlar ADD COLUMN IF NOT EXISTS embedding vector(768);"))

                    # Eski kurulumlarda 12 haneli noktalı GTİP değerlerini kesen VARCHAR(14) kolonunu genişlet.
                    conn.execute(text("ALTER TABLE gtip_rules ALTER COLUMN target_gtip TYPE VARCHAR(30);"))
                    conn.commit()
                    logger.info("[SQLAlchemy ORM] PostgreSQL şema kolonları (ALTER TABLE IF NOT EXISTS) doğrulandı.")
            except Exception as ex_pg_mig:
                logger.warning(f"[SQLAlchemy ORM] PostgreSQL auto-migration uyarısı: {ex_pg_mig}")

        # 2b. SQLite Şema Güncellemesi (Eski yerel db dosyalarında eksik kolon varsa dinamik ekle)
        if engine.dialect.name == "sqlite":
            try:
                with engine.connect() as conn:
                    # tgtc_gtip
                    try:
                        cols_gtip = [r[1] for r in conn.execute(text("PRAGMA table_info(tgtc_gtip)")).fetchall()]
                        if "chapter_code" not in cols_gtip and cols_gtip:
                            conn.execute(text("ALTER TABLE tgtc_gtip ADD COLUMN chapter_code VARCHAR(10)"))
                        if "embedding" not in cols_gtip and cols_gtip:
                            conn.execute(text("ALTER TABLE tgtc_gtip ADD COLUMN embedding TEXT"))
                        if "gecerlilik_baslangic" not in cols_gtip and cols_gtip:
                            conn.execute(text("ALTER TABLE tgtc_gtip ADD COLUMN gecerlilik_baslangic VARCHAR(30) DEFAULT '2026-01-01'"))
                        if "gecerlilik_bitis" not in cols_gtip and cols_gtip:
                            conn.execute(text("ALTER TABLE tgtc_gtip ADD COLUMN gecerlilik_bitis VARCHAR(30)"))
                        if "kaynak_resmi_gazete_no" not in cols_gtip and cols_gtip:
                            conn.execute(text("ALTER TABLE tgtc_gtip ADD COLUMN kaynak_resmi_gazete_no VARCHAR(50)"))
                    except Exception:
                        pass
                    
                    # tgtc_notes
                    try:
                        cols_notes = [r[1] for r in conn.execute(text("PRAGMA table_info(tgtc_notes)")).fetchall()]
                        if "title" not in cols_notes and cols_notes:
                            conn.execute(text("ALTER TABLE tgtc_notes ADD COLUMN title VARCHAR(255)"))
                        if "note_type" not in cols_notes and cols_notes:
                            conn.execute(text("ALTER TABLE tgtc_notes ADD COLUMN note_type VARCHAR(50) DEFAULT 'GENERAL'"))
                        if "embedding" not in cols_notes and cols_notes:
                            conn.execute(text("ALTER TABLE tgtc_notes ADD COLUMN embedding TEXT"))
                    except Exception:
                        pass

                    # gumruk_emsal_kararlar
                    try:
                        cols_emsal = [r[1] for r in conn.execute(text("PRAGMA table_info(gumruk_emsal_kararlar)")).fetchall()]
                        if "chapter_code" not in cols_emsal and cols_emsal:
                            conn.execute(text("ALTER TABLE gumruk_emsal_kararlar ADD COLUMN chapter_code VARCHAR(10)"))
                        if "embedding" not in cols_emsal and cols_emsal:
                            conn.execute(text("ALTER TABLE gumruk_emsal_kararlar ADD COLUMN embedding TEXT"))
                    except Exception:
                        pass
                    conn.commit()
            except Exception as ex_sqlite:
                logger.debug(f"[SQLAlchemy ORM] SQLite auto-migration uyarısı: {ex_sqlite}")

        # 3. PostgreSQL HNSW Vektör İndeksleri
        if engine.dialect.name == "postgresql":
            try:
                with engine.connect() as conn:
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_tgtc_gtip_embedding_hnsw 
                        ON tgtc_gtip USING hnsw (embedding vector_cosine_ops);
                    """))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_gumruk_emsal_embedding_hnsw 
                        ON gumruk_emsal_kararlar USING hnsw (embedding vector_cosine_ops);
                    """))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_tgtc_notes_embedding_hnsw 
                        ON tgtc_notes USING hnsw (embedding vector_cosine_ops);
                    """))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_mevzuat_embedding_hnsw 
                        ON gumruk_mevzuat_maddeleri USING hnsw (icerik_vektor vector_cosine_ops);
                    """))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_emsal_btb_embedding_hnsw 
                        ON emsal_btb_kararlari USING hnsw (icerik_vektor vector_cosine_ops);
                    """))
                    conn.commit()
                    logger.info("[SQLAlchemy ORM] PostgreSQL HNSW vektör kosinüs indeksleri doğrulandı.")
            except Exception as ex_idx:
                logger.debug(f"[SQLAlchemy ORM] HNSW index uyarısı: {ex_idx}")

        # 🚀 OTOMATİK CLOUD SQL TOHUMLAYICI (2026 TGTC Tarife Ağacı) 🚀
        try:
            with SessionLocal() as session:
                count_gtip = session.query(TgtcGtipModel).count()
                auto_seed_enabled = os.getenv("SKIP_TGTC_AUTO_SEED", "false").lower() != "true"
                if count_gtip == 0 and auto_seed_enabled:
                    logger.info("[SQLAlchemy ORM] Cloud SQL Tarife Ağacı boş! '2026 TGTC' dizininden 01-99 Fasıllar ve GTİP tohumlaması başlatılıyor...")
                    from scripts.populate_tgtc_cloudsql import extract_gir_rules, extract_chapter_notes, populate_gtip_tree
                    extract_gir_rules(session)
                    extract_chapter_notes(session)
                    populate_gtip_tree(session)
                    logger.info("[SQLAlchemy ORM] 2026 TGTC Tarife Ağacı (01-99 Fasıllar) başarıyla Cloud SQL'e yüklendi!")
                elif count_gtip > 0:
                    logger.info(f"[SQLAlchemy ORM] 2026 TGTC Tarife Ağacı mevcut ({count_gtip} kayıt aktif).")
                else:
                    logger.info("[SQLAlchemy ORM] TGTC otomatik seed kontrollü yıllık job için atlandı.")
        except Exception as ex_seed:
            logger.warning(f"[SQLAlchemy ORM] TGTC Tohumlama uyarısı: {ex_seed}")

        # 🚀 OTOMATİK DİNAMİK GTİP KURAL TOHUMLAYICI (gcp_architecture_report.md) 🚀
        try:
            with SessionLocal() as session:
                count_rules = session.query(GtipRuleModel).count()
                if count_rules == 0:
                    sample_rules = [
                        GtipRuleModel(
                            parent_heading="8471",
                            target_gtip="8471.30.00.00.11",
                            parametre_adi="weight",
                            kosul_operatoru="<=",
                            esik_deger="10kg",
                            soru_metni="Cihazın net ağırlığı klavye ve ekran dahil 10 kg'ı geçiyor mu?",
                            secenekler=json.dumps([
                                {"id": "opt_le_10kg", "value": "10kg", "label": "Ağırlık 10 kg veya altında (Portatif / Dizüstü)"},
                                {"id": "opt_gt_10kg", "value": "10.01kg", "label": "Ağırlık 10 kg'dan fazla (Masaüstü / Sunucu)"}
                            ], ensure_ascii=False),
                            oncelik=1
                        ),
                        GtipRuleModel(
                            parent_heading="8471",
                            target_gtip="8471.30.00.00.11",
                            parametre_adi="has_display_and_keyboard",
                            kosul_operatoru="==",
                            esik_deger="true",
                            soru_metni="Cihaz en azından bir merkezi işlem birimi, bir klavye ve bir ekrandan mı oluşuyor?",
                            secenekler=json.dumps([
                                {"id": "opt_has_both", "value": "true", "label": "Evet, entegre ekran ve klavyesi var"},
                                {"id": "opt_no_both", "value": "false", "label": "Hayır, harici birimler gerekiyor"}
                            ], ensure_ascii=False),
                            oncelik=2
                        ),
                        GtipRuleModel(
                            parent_heading="5208",
                            target_gtip="5208.11.90.00.00",
                            parametre_adi="cotton_ratio",
                            kosul_operatoru=">=",
                            esik_deger="85%",
                            soru_metni="Kumaşın ağırlık itibariyle pamuk oranı en az %85 mi?",
                            secenekler=json.dumps([
                                {"id": "opt_cotton_gte_85", "value": "85%", "label": "Evet, %85 veya daha fazla pamuk içerir"},
                                {"id": "opt_cotton_lt_85", "value": "84.99%", "label": "Hayır, pamuk oranı %85'in altında"}
                            ], ensure_ascii=False),
                            oncelik=1
                        )
                    ]
                    session.add_all(sample_rules)
                    session.commit()
                    logger.info("[SQLAlchemy ORM] gtip_rules tablosu başlangıç kuralları ile tohumlandı.")
        except Exception as ex_rule_seed:
            logger.warning(f"[SQLAlchemy ORM] gtip_rules tohumlama uyarısı: {ex_rule_seed}")
            
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

# ==============================================================================
# HİBRİT ARAMA VE RRF (RECIPROCAL RANK FUSION) YARDIMCI FONKSİYONLARI
# ==============================================================================

def compute_rrf_score(ranks: List[int], k: int = 60) -> float:
    """
    Reciprocal Rank Fusion (RRF) skorunu hesaplar:
    RRF_Score(d) = sum(1 / (k + rank_i))
    """
    score = 0.0
    for r in ranks:
        if r is not None and r > 0:
            score += 1.0 / (k + r)
    return score


def _normalize_search_text(value: Any) -> str:
    """Türkçe aramada ASCII/Türkçe klavye farklarını aynı sözcüğe indirger."""
    return str(value or "").lower().translate(str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    }))

def search_chapter_notes_and_exclusions(
    session: Session, 
    chapter_codes: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    Hedeflenen fasılların Bakanlık Genel İzahnamesini ve 'Bu fasıl kapsamaz...' Dışlama Notlarını çeker.
    Dönen sözlük formatı: { '64': {'general_notes': '...', 'exclusions': ['Kauçuk ayakkabı tabanı...', ...]} }
    """
    result: Dict[str, Dict[str, Any]] = {}
    clean_chaps = [str(c).zfill(2) for c in chapter_codes if str(c).strip()]
    if not clean_chaps:
        return result

    try:
        notes = session.query(TgtcNoteModel).filter(
            TgtcNoteModel.chapter_code.in_(clean_chaps)
        ).all()

        for note in notes:
            chap = str(note.chapter_code).zfill(2)
            if chap not in result:
                result[chap] = {"general_notes": "", "exclusions": []}

            text_content = note.text or ""
            if note.note_type == "EXCLUSION":
                result[chap]["exclusions"].append(text_content)
            else:
                # Metin içerisinde 'kapsamaz', 'dahil değildir' fıkralarını otomatik tespit et
                result[chap]["general_notes"] += f"\n{text_content}".strip()
                lines = text_content.split("\n")
                for line in lines:
                    line_lower = line.lower()
                    if any(kw in line_lower for kw in ["kapsamaz", "dahil değildir", "bu fasla girmez", "hariçtir"]):
                        result[chap]["exclusions"].append(line.strip())
    except Exception as e:
        logger.warning(f"[DB Notes Search] İzahname/Dışlama notu sorgu uyarısı: {e}")

    # Fallback: Yerel json rules & notes
    if not result:
        try:
            from api.db.tgtc_knowledge_base import load_tgtc_rules_and_notes
            rules_db = load_tgtc_rules_and_notes()
            all_notes = rules_db.get("fasil_notlari", {})
            for chap in clean_chaps:
                note_text = all_notes.get(chap, "")
                if note_text:
                    exclusions = []
                    for sentence in note_text.split("."):
                        if any(kw in sentence.lower() for kw in ["kapsamaz", "dahil değildir", "hariç"]):
                            exclusions.append(sentence.strip() + ".")
                    result[chap] = {
                        "general_notes": note_text,
                        "exclusions": exclusions
                    }
        except Exception:
            pass

    return result


def get_heading_notes(session: Session, heading_code: str) -> Dict[str, Any]:
    """Bir pozisyonun fasıl notlarını yerel servis çağrısıyla döndürür."""
    digits = re.sub(r"\D", "", str(heading_code or ""))
    if len(digits) < 2:
        return {"general_notes": "", "exclusions": []}
    return search_chapter_notes_and_exclusions(session, [digits[:2]]).get(
        digits[:2], {"general_notes": "", "exclusions": []}
    )


def calculate_dynamic_candidate_score(
    tgtc_similarity: float,
    btb_support: float = 0.0,
    verified_btb_count: int = 0,
) -> float:
    """BTB yokluğunda TGTC kanıtını seyrelmeden koruyan nihai puan."""
    tgtc = min(1.0, max(0.0, float(tgtc_similarity or 0.0)))
    if int(verified_btb_count or 0) < 1:
        return tgtc
    btb = min(1.0, max(0.0, float(btb_support or 0.0)))
    return round(tgtc * 0.40 + btb * 0.60, 12)


def upsert_tgtc_temporal_version(
    session: Session,
    *,
    gtip_code: str,
    description: str,
    effective_from: str,
    source_gazette_no: Optional[str] = None,
    level: Optional[str] = None,
    tax_rate: Optional[str] = None,
    unit: Optional[str] = None,
) -> TgtcGtipVersionModel:
    """Yeni cetvel satırını ekler, değişen eski sürümün bitişini kapatır."""
    import datetime as _datetime

    code = re.sub(r"\D", "", str(gtip_code or ""))
    if len(code) not in {2, 4, 6, 8, 10, 12}:
        raise ValueError(f"Geçersiz tarife kodu: {gtip_code}")
    resolved_level = level or ({2: "CHAPTER", 4: "HEADING", 6: "SUBHEADING"}.get(len(code), "GTIP"))
    parent = None if len(code) == 2 else code[: {4: 2, 6: 4}.get(len(code), 6)]
    active = session.query(TgtcGtipVersionModel).filter(
        TgtcGtipVersionModel.gtip_code == code,
        TgtcGtipVersionModel.gecerlilik_bitis.is_(None),
    ).order_by(TgtcGtipVersionModel.gecerlilik_baslangic.desc()).first()
    unchanged = active and (
        active.description == description and active.tax_rate == tax_rate and active.unit == unit
    )
    if unchanged:
        active.kaynak_resmi_gazete_no = source_gazette_no or active.kaynak_resmi_gazete_no
        return active
    if active:
        start = _datetime.date.fromisoformat(effective_from)
        active.gecerlilik_bitis = (start - _datetime.timedelta(days=1)).isoformat()

    version = TgtcGtipVersionModel(
        gtip_code=code, level=resolved_level, chapter_code=code[:2], parent_code=parent,
        description=description, tax_rate=tax_rate, unit=unit,
        gecerlilik_baslangic=effective_from,
        kaynak_resmi_gazete_no=source_gazette_no,
    )
    session.add(version)

    current = session.get(TgtcGtipModel, code)
    if current is None:
        current = TgtcGtipModel(gtip_code=code, description=description, level=resolved_level)
        session.add(current)
    current.level = resolved_level
    current.chapter_code = code[:2]
    current.parent_code = parent
    current.description = description
    current.tax_rate = tax_rate
    current.unit = unit
    current.is_active = True
    current.gecerlilik_baslangic = effective_from
    current.gecerlilik_bitis = None
    current.kaynak_resmi_gazete_no = source_gazette_no
    return version


def search_recent_customs_legislation(
    session: Session,
    query_text: str,
    min_date: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Son altı yıllık gümrük mevzuatı maddelerinde açıklanabilir sözcük araması yapar."""
    tokens = list(dict.fromkeys(
        token for token in re.findall(r"[0-9a-zA-ZçğıöşüÇĞİÖŞÜ]+", query_text.lower())
        if len(token) >= 4
    ))[:8]
    if not tokens:
        return []

    try:
        query = session.query(GumrukMevzuatMaddesiModel).filter(
            GumrukMevzuatMaddesiModel.tarih >= min_date,
            or_(*[GumrukMevzuatMaddesiModel.madde_metni.ilike(f"%{token}%") for token in tokens]),
        )
        records = query.order_by(GumrukMevzuatMaddesiModel.tarih.desc()).limit(100).all()
    except Exception as exc:
        logger.warning(f"[Mevzuat Search] Son altı yıllık mevzuat sorgusu başarısız: {exc}")
        return []

    scored = []
    for record in records:
        searchable = f"{record.kanun_no} {record.madde_kodu} {record.madde_metni}".lower()
        overlap = sum(1 for token in tokens if token in searchable)
        scored.append((overlap, str(record.tarih), record))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

    return [
        {
            "reference_no": f"{record.kanun_no}/{record.madde_kodu}",
            "title": f"{record.kanun_no} - {record.madde_kodu}",
            "publication_date": str(record.tarih),
            "excerpt": str(record.madde_metni)[:1200],
            "source_url": record.kaynak_url,
        }
        for _, _, record in scored[:top_k]
    ]

def hybrid_search_headings_and_gtip(
    session: Session,
    query_text: str,
    query_vector: Optional[List[float]] = None,
    allowed_chapters: Optional[List[str]] = None,
    search_level: Optional[str] = None,
    parent_codes: Optional[List[str]] = None,
    as_of_date: Optional[str] = None,
    top_k: int = 10,
    rrf_k: int = 60
) -> List[Dict[str, Any]]:
    """
    Cloud SQL PostgreSQL / SQLite üzerinde Hibrit Arama (Dense pgvector + Sparse Text Search)
    ve Reciprocal Rank Fusion (RRF) uygulayarak en uygun TGTC düğümlerini döner.

    ``search_level`` HEADING, SUBHEADING veya GTIP olduğunda yalnızca o ağaç
    seviyesinde arama yapılır. ``parent_codes`` bir önceki aşamada kilitlenen
    dallardır; böylece farklı pozisyonların "Diğer" satırları aynı aday havuzuna
    giremez. Eski çağrılar için parametreler opsiyoneldir.
    """
    clean_query = _normalize_search_text(query_text.strip())
    raw_tokens = [w for w in re.findall(r"[0-9a-z]+", clean_query) if len(w) > 2]
    common_suffixes = ("lari", "leri", "lar", "ler", "nin", "nun", "in", "un", "li", "lu", "lik", "luk", "i", "u")
    stemmed_tokens = []
    for token in raw_tokens:
        stemmed_tokens.append(token)
        suffix = next((value for value in common_suffixes if token.endswith(value) and len(token) - len(value) >= 4), None)
        if suffix:
            stemmed_tokens.append(token[:-len(suffix)])
    query_tokens = list(dict.fromkeys(stemmed_tokens))
    clean_chaps = [str(c).zfill(2) for c in (allowed_chapters or []) if str(c).strip()]
    target_level = str(search_level or "").upper() or None
    clean_parents = [re.sub(r"\D", "", str(code)) for code in (parent_codes or [])]
    effective_date = str(as_of_date or "")

    def code_digits(value: Any) -> str:
        return re.sub(r"\D", "", str(value or ""))

    def belongs_to_locked_branch(code: str) -> bool:
        return not clean_parents or any(code.startswith(parent) for parent in clean_parents)

    def add_candidate(item: Dict[str, Any]) -> None:
        code = code_digits(item.get("gtip_code"))
        if not code or code in seen_codes or not belongs_to_locked_branch(code):
            return
        seen_codes.add(code)
        item["gtip_code"] = code
        candidate_records.append(item)

    # 1. SQL Aday Kümesi ve TGTC 4-Haneli Pozisyonlar
    candidate_records = []
    seen_codes = set()

    try:
        query = session.query(TgtcGtipModel).filter(TgtcGtipModel.is_active == True)
        if clean_chaps:
            query = query.filter(TgtcGtipModel.chapter_code.in_(clean_chaps))
        if effective_date:
            query = query.filter(
                or_(TgtcGtipModel.gecerlilik_baslangic.is_(None), TgtcGtipModel.gecerlilik_baslangic <= effective_date),
                or_(TgtcGtipModel.gecerlilik_bitis.is_(None), TgtcGtipModel.gecerlilik_bitis >= effective_date),
            )
        # Aday kümesini Python'da tüm tarife ağacını dolaşarak değil, indeksli
        # level/chapter/parent alanlarıyla SQL tarafında daralt. Eski veri
        # yüklemelerinde bazı 6 haneli alt pozisyonlar ayrı SUBHEADING satırı,
        # bazıları ise doğrudan 12 haneli yaprak olarak bulunduğundan iki kayıt
        # türü aynı kilitli pozisyon içinde birlikte okunur.
        if target_level == "HEADING":
            query = query.filter(TgtcGtipModel.level == "HEADING")
        elif target_level == "GTIP":
            query = query.filter(TgtcGtipModel.level == "GTIP")
            if clean_parents:
                query = query.filter(or_(*[
                    TgtcGtipModel.gtip_code.like(f"{parent}%")
                    for parent in clean_parents
                ]))
        elif target_level == "SUBHEADING":
            subheading_query = query.filter(
                TgtcGtipModel.level.in_(["SUBHEADING", "GTIP"])
            )
            if clean_parents:
                subheading_query = subheading_query.filter(or_(*[
                    TgtcGtipModel.gtip_code.like(f"{parent}%")
                    for parent in clean_parents
                ]))
            db_items = subheading_query.all()
        if target_level != "SUBHEADING":
            db_items = query.all()
        for it in db_items:
            code = code_digits(it.gtip_code)
            if target_level == "HEADING" and len(code) != 4:
                continue
            if target_level == "SUBHEADING" and len(code) not in {6, 8, 10, 12}:
                continue
            if target_level == "GTIP" and len(code) != 12:
                continue
            if target_level == "SUBHEADING" and len(code) > 6:
                code = code[:6]
            add_candidate({
                "gtip_code": code,
                "description": it.description or "",
                "chapter_code": it.chapter_code or code[:2],
                "level": target_level or it.level,
                "tax_rate": it.tax_rate,
                "unit": it.unit,
                # Türetilmiş 6-haneli düğümde yaprak embedding'i yasal alt
                # pozisyon metnini temsil etmediği için dense kanıt sayılmaz.
                "embedding": it.embedding if len(code_digits(it.gtip_code)) == len(code) else None,
            })
    except Exception as ex_db:
        logger.debug(f"[Hybrid DB Query] {ex_db}")

    # TGTC 4-Haneli Pozisyonlar sözlüğü ile zenginleştir (01-97 Fasıllar)
    try:
        from api.db.tgtc_knowledge_base import get_local_tgtc_headings
        headings_dict = get_local_tgtc_headings()
        for code, desc in headings_dict.items():
            code = code_digits(code)
            if target_level not in {None, "HEADING"} or len(code) != 4:
                continue
            chap = str(code)[:2].zfill(2)
            if clean_chaps and chap not in clean_chaps:
                continue
            add_candidate({
                "gtip_code": code,
                "description": desc,
                "chapter_code": chap,
                "level": "HEADING",
                "tax_rate": None,
                "unit": None,
                "embedding": None,
            })
    except Exception as ex_head:
        logger.debug(f"[Hybrid Headings Load] {ex_head}")

    if not candidate_records:
        return []

    # Pozisyon aramasında fasıl notları da aranabilir metne dahil edilir, fakat
    # resmi pozisyon açıklaması çıktı alanında değiştirilmez.
    notes_by_chapter: Dict[str, str] = {}
    if target_level == "HEADING":
        for chapter, payload in search_chapter_notes_and_exclusions(session, clean_chaps).items():
            notes_by_chapter[chapter] = "\n".join([
                str(payload.get("general_notes") or ""),
                " ".join(str(value) for value in payload.get("exclusions", [])),
            ])
    for item in candidate_records:
        chapter_notes = notes_by_chapter.get(str(item.get("chapter_code") or "").zfill(2), "")
        code = str(item.get("gtip_code") or "")
        subheading_context = _load_subheading_contexts().get(code, {})
        item["branch_context"] = str(subheading_context.get("description") or "")
        item["required_terms"] = [
            _normalize_search_text(term)
            for term in subheading_context.get("required_terms", [])
            if str(term).strip()
        ]
        item["missing_qualifier_penalty"] = float(
            subheading_context.get("missing_qualifier_penalty") or 0.0
        )
        relevant_note_lines = " ".join(
            line for line in chapter_notes.splitlines() if code and code in re.sub(r"\D", "", line)
        )
        item["searchable_text"] = " ".join([
            str(item.get("description") or ""),
            item["branch_context"],
            relevant_note_lines,
        ])

    # 2. Sparse (BM25 / Token Overlap & GIR 3a Specificity) Sıralaması
    token_document_frequency = {
        token: sum(
            1 for item in candidate_records
            if token in _normalize_search_text(item.get("searchable_text"))
        )
        for token in query_tokens
    }
    token_weights = {
        token: 1.0 + math.log((len(candidate_records) + 1) / (frequency + 1))
        for token, frequency in token_document_frequency.items()
    }

    sparse_scores: List[Tuple[float, Any]] = []
    for item in candidate_records:
        desc_lower = _normalize_search_text(item["searchable_text"])
        # Nadir ve ayırt edici terimler (örn. "kettle") genel terimlerden
        # (örn. "elektrikli") daha yüksek ağırlık alır.
        match_count = sum(token_weights[token] for token in query_tokens if token in desc_lower)
        if match_count > 0:
            # Artık ("Diğer") pozisyon yasal bir daldır. Yapay ceza uygulanmaz;
            # seçim yalnızca sorgu kanıtı ve üst dal kilidi içinde yapılır.
            score = match_count / (len(query_tokens) + 1.0)
            required_terms = item.get("required_terms") or []
            if required_terms and not any(term in clean_query for term in required_terms):
                score -= float(item.get("missing_qualifier_penalty") or 0.0)
            if score <= 0.0:
                continue
            sparse_scores.append((score, item))

    sparse_scores.sort(key=lambda x: x[0], reverse=True)
    sparse_ranks = {item["gtip_code"]: rank + 1 for rank, (_, item) in enumerate(sparse_scores)}

    # 3. Dense (Vektör Kosinüs Benzerliği) Sıralaması
    dense_scores: List[Tuple[float, Any]] = []
    if query_vector is not None:
        def _cosine_sim(v1: List[float], v2: List[float]) -> float:
            if not v1 or not v2 or len(v1) != len(v2):
                return 0.0
            dot = sum(a * b for a, b in zip(v1, v2))
            norm_a = math.sqrt(sum(a * a for a in v1))
            norm_b = math.sqrt(sum(b * b for a, b in zip(v2, v2))) # Placeholder fix
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        for item in candidate_records:
            emb = item.get("embedding")
            if isinstance(emb, list) and emb:
                sim = _cosine_sim(query_vector, emb)
                if sim > 0.0:
                    dense_scores.append((sim, item))

        dense_scores.sort(key=lambda x: x[0], reverse=True)
    dense_ranks = {item["gtip_code"]: rank + 1 for rank, (_, item) in enumerate(dense_scores)}

    # 4. Reciprocal Rank Fusion (RRF) Birleştirme
    rrf_candidates: Dict[str, Dict[str, Any]] = {}
    candidate_items = {item["gtip_code"]: item for item in candidate_records}

    # Tüm adayların Sparse & Dense Rank'lerini birleştir
    all_gtips = set(sparse_ranks.keys()).union(set(dense_ranks.keys()))
    if not all_gtips:
        # Kilitli bir yasal dalın yaprakları çoğu zaman yalnız "Çocuklar için"
        # ve "Diğerleri" gibi üst bağlamdan bağımsız metinler taşır. Bu durumda
        # dalı boş saymak yerine eşit skorlu seçenekleri discriminator'a ver;
        # kilit yoksa kanıtsız/arbitrary sonuç üretme.
        if clean_parents and target_level in {"SUBHEADING", "GTIP"}:
            return [
                {
                    "gtip_code": item["gtip_code"],
                    "description": item.get("description", ""),
                    "branch_context": item.get("branch_context", ""),
                    "chapter": item.get("chapter_code") or item["gtip_code"][:2],
                    "heading": item["gtip_code"][:4],
                    "level": item.get("level", target_level),
                    "tax_rate": item.get("tax_rate"),
                    "unit": item.get("unit"),
                    "rrf_score": 0.0,
                    "similarity_score": 0.5,
                    "sparse_rank": None,
                    "dense_rank": None,
                }
                for item in sorted(candidate_records, key=lambda value: value["gtip_code"])
            ][:top_k]
        return []

    for gtip in all_gtips:
        item = candidate_items.get(gtip)
        if not item:
            continue
        s_rank = sparse_ranks.get(gtip)
        d_rank = dense_ranks.get(gtip)

        ranks_to_fuse = []
        if s_rank:
            ranks_to_fuse.append(s_rank)
        if d_rank:
            ranks_to_fuse.append(d_rank)

        # RRF Skoru hesabı
        rrf = compute_rrf_score(ranks_to_fuse, k=rrf_k)
        
        # Dense ve Sparse ham benzerlikleri
        dense_sim = next((score for score, it in dense_scores if it["gtip_code"] == gtip), None)
        sparse_sim = next((score for score, it in sparse_scores if it["gtip_code"] == gtip), None)

        if dense_sim is not None and sparse_sim is not None:
            combined_sim = dense_sim * 0.6 + sparse_sim * 0.4
        elif dense_sim is not None:
            combined_sim = dense_sim
        else:
            combined_sim = float(sparse_sim or 0.0)
        normalized_sim = round(min(0.98, max(0.0, combined_sim + rrf * 5.0)), 4)

        rrf_candidates[gtip] = {
            "gtip_code": gtip,
            "description": item.get("description", ""),
            "branch_context": item.get("branch_context", ""),
            "chapter": item.get("chapter_code") or gtip[:2],
            "heading": gtip[:4],
            "level": item.get("level", "HEADING"),
            "tax_rate": item.get("tax_rate"),
            "unit": item.get("unit"),
            "rrf_score": rrf,
            "similarity_score": normalized_sim,
            "sparse_rank": s_rank,
            "dense_rank": d_rank
        }

    # RRF skoruna göre sırala ve top_k kadarını döner
    sorted_results = sorted(rrf_candidates.values(), key=lambda x: (x["rrf_score"], x["similarity_score"]), reverse=True)
    return sorted_results[:top_k]
