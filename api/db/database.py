"""
GCP Cloud SQL (PostgreSQL + pgvector) SQLAlchemy 2.0 ORM Veritabanı Modülü.
Tüm FastAPI uç noktaları, Hiyerarşik Hibrit RAG motoru ve durum depoları için
tekil (Singleton) ORM Engine, SessionLocal, Dependency get_db() ve
vektör/metin hibrit arama fonksiyonları sağlar.
"""
import os
import json
import logging
import math
from typing import Generator, List, Dict, Any, Optional, Tuple
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    Text, DateTime, func, text, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

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
    embedding = Column(VectorType(768), nullable=True)           # 768d text-embedding-005 vektörü

def get_database_url() -> str:
    """GCP Cloud SQL PostgreSQL bağlantı dizesini döndürür."""
    env_db_url = os.getenv("DATABASE_URL")
    if env_db_url and env_db_url.strip():
        return env_db_url.strip()

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
connect_args = {"connect_timeout": 5} if DATABASE_URL.startswith("postgresql") else {}
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=2,        # Cloud Run instance başına düşük pool size (serverless optimization)
    max_overflow=3,     # Yoğun yükte max +3 connection
    pool_recycle=600,   # Cloud SQL connection reuse lifetime (10 dakika)
    pool_timeout=30,    # Max wait time for a connection
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
                    
                    # tgtc_notes
                    conn.execute(text("ALTER TABLE tgtc_notes ADD COLUMN IF NOT EXISTS note_type VARCHAR(50) DEFAULT 'GENERAL';"))
                    conn.execute(text("ALTER TABLE tgtc_notes ADD COLUMN IF NOT EXISTS title VARCHAR(255);"))
                    conn.execute(text("ALTER TABLE tgtc_notes ADD COLUMN IF NOT EXISTS embedding vector(768);"))
                    
                    # gumruk_emsal_kararlar
                    conn.execute(text("ALTER TABLE gumruk_emsal_kararlar ADD COLUMN IF NOT EXISTS chapter_code VARCHAR(10);"))
                    conn.execute(text("ALTER TABLE gumruk_emsal_kararlar ADD COLUMN IF NOT EXISTS valid_until VARCHAR(20) DEFAULT '9999-12-31';"))
                    conn.execute(text("ALTER TABLE gumruk_emsal_kararlar ADD COLUMN IF NOT EXISTS embedding vector(768);"))
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
                    conn.commit()
                    logger.info("[SQLAlchemy ORM] PostgreSQL HNSW vektör kosinüs indeksleri doğrulandı.")
            except Exception as ex_idx:
                logger.debug(f"[SQLAlchemy ORM] HNSW index uyarısı: {ex_idx}")

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
                count_gtip = session.query(TgtcGtipModel).count()
                if count_gtip == 0:
                    logger.info("[SQLAlchemy ORM] Cloud SQL Tarife Ağacı boş! '2026 TGTC' dizininden 01-99 Fasıllar ve GTİP tohumlaması başlatılıyor...")
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

def hybrid_search_headings_and_gtip(
    session: Session,
    query_text: str,
    query_vector: Optional[List[float]] = None,
    allowed_chapters: Optional[List[str]] = None,
    top_k: int = 10,
    rrf_k: int = 60
) -> List[Dict[str, Any]]:
    """
    Cloud SQL PostgreSQL / SQLite üzerinde Hibrit Arama (Dense pgvector + Sparse Text Search)
    ve Reciprocal Rank Fusion (RRF) uygulayarak en uygun TGTC pozisyonlarını ve 12-haneli GTİP'leri döner.
    """
    clean_query = query_text.strip().lower()
    query_tokens = [w for w in clean_query.split() if len(w) > 2]
    # 1. SQL Aday Kümesi ve TGTC 4-Haneli Pozisyonlar
    candidate_records = []
    seen_codes = set()

    try:
        query = session.query(TgtcGtipModel).filter(TgtcGtipModel.is_active == True)
        if clean_chaps:
            query = query.filter(TgtcGtipModel.chapter_code.in_(clean_chaps))
        db_items = query.all()
        for it in db_items:
            if it.gtip_code not in seen_codes:
                seen_codes.add(it.gtip_code)
                candidate_records.append({
                    "gtip_code": it.gtip_code,
                    "description": it.description or "",
                    "chapter_code": it.chapter_code or it.gtip_code[:2],
                    "level": it.level,
                    "embedding": it.embedding
                })
    except Exception as ex_db:
        logger.debug(f"[Hybrid DB Query] {ex_db}")

    # TGTC 4-Haneli Pozisyonlar sözlüğü ile zenginleştir (01-97 Fasıllar)
    try:
        from api.db.tgtc_knowledge_base import get_local_tgtc_headings
        headings_dict = get_local_tgtc_headings()
        for code, desc in headings_dict.items():
            chap = str(code)[:2].zfill(2)
            if clean_chaps and chap not in clean_chaps:
                continue
            if code not in seen_codes:
                seen_codes.add(code)
                candidate_records.append({
                    "gtip_code": code,
                    "description": desc,
                    "chapter_code": chap,
                    "level": "HEADING",
                    "embedding": None
                })
    except Exception as ex_head:
        logger.debug(f"[Hybrid Headings Load] {ex_head}")

    if not candidate_records:
        return []

    # 2. Sparse (BM25 / Token Overlap & GIR 3a Specificity) Sıralaması
    sparse_scores: List[Tuple[float, Any]] = []
    for item in candidate_records:
        desc_lower = (item["description"] or "").lower()
        match_count = sum(2.0 for token in query_tokens if token in desc_lower)
        if match_count > 0:
            # GİR 3(a) Özellik İlkesi: "Diğer ..." genel artık pozisyonlar özel pozisyonların gerisinde kalmalıdır
            is_residual = desc_lower.startswith("diğer") or desc_lower.startswith("diger")
            specificity_factor = 0.5 if is_residual else 1.0
            score = (match_count * specificity_factor) / (len(query_tokens) + 1.0)
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
                dense_scores.append((sim, item))

        dense_scores.sort(key=lambda x: x[0], reverse=True)
    dense_ranks = {item["gtip_code"]: rank + 1 for rank, (_, item) in enumerate(dense_scores)}

    # 4. Reciprocal Rank Fusion (RRF) Birleştirme
    rrf_candidates: Dict[str, Dict[str, Any]] = {}
    candidate_items = {item["gtip_code"]: item for item in candidate_records}

    # Tüm adayların Sparse & Dense Rank'lerini birleştir
    all_gtips = set(sparse_ranks.keys()).union(set(dense_ranks.keys()))
    if not all_gtips:
        # Fallback: ilk kayıtlar
        all_gtips = set(item["gtip_code"] for item in candidate_records[:top_k])

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
        dense_sim = next((score for score, it in dense_scores if it["gtip_code"] == gtip), 0.70)
        sparse_sim = next((score for score, it in sparse_scores if it["gtip_code"] == gtip), 0.50)
        
        # Ağırlıklı nihai benzerlik (Sparse + Dense)
        combined_sim = (dense_sim * 0.6) + (sparse_sim * 0.4)
        normalized_sim = round(min(0.98, max(0.50, combined_sim + rrf * 5.0)), 4)

        rrf_candidates[gtip] = {
            "gtip_code": gtip,
            "description": item.get("description", ""),
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
