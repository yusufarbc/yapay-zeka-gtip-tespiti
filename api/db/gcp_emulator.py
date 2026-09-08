"""
GCP Cloud SQL, Vertex AI Vector Search ve Firestore/Redis Emülatörü.
Cloud Run worker'ları arasında SQLite tabanlı paylaşımlı durum (Shared State)
ve Vertex AI Vector Search için embedding/vektör arama motoru sağlar.

Arama Stratejisi (Öncelik Sırası):
1. text-embedding-005 ile gerçek Cosine Similarity (API key varsa)
2. Jaccard Token Overlap (offline/test fallback)
"""
import os
import json
import math
import sqlite3
import logging
import datetime
import re
import time
from typing import Dict, List, Any, Optional

logger = logging.getLogger("GCPEmulator")

import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(tempfile.gettempdir(), "gtip_app_runtime_data")
DB_PATH = os.path.join(DATA_DIR, "audit_logs.db")
VECTOR_INDEX_PATH = os.path.join(DATA_DIR, "vector_index.json")
BTB_DB_PATH = os.path.join(DATA_DIR, "official_btb_database.json")

from sqlalchemy import Column, String, Text, DateTime, Boolean, func
from api.db.database import Base, engine, SessionLocal

class SessionStateModel(Base):
    """SQLAlchemy ORM Model for Session and HITL state storage."""
    __tablename__ = "session_state"

    session_id = Column(String(255), primary_key=True)
    state_data = Column(Text, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())





class CloudSQLStateStore:
    """GCP Cloud SQL (PostgreSQL) SQLAlchemy 2.0 ORM tabanlı Durum Yöneticisi."""
    def __init__(self):
        try:
            Base.metadata.create_all(bind=engine)
            self.SessionMaker = SessionLocal
            logger.info("[GCP Cloud SQL] SQLAlchemy 2.0 ORM tabloları başarıyla oluşturuldu ve doğrulandı.")
        except Exception as e:
            logger.warning(f"[CloudSQLStateStore] ORM Başlatma Uyarısı: {e}")
            self.SessionMaker = SessionLocal

    def save_state(self, session_id: str, data: Dict[str, Any]):
        if not self.SessionMaker:
            return
        session = self.SessionMaker()
        try:
            record = session.query(SessionStateModel).filter_by(session_id=session_id).first()
            if record:
                record.state_data = json.dumps(data, ensure_ascii=False)
            else:
                record = SessionStateModel(
                    session_id=session_id,
                    state_data=json.dumps(data, ensure_ascii=False)
                )
                session.add(record)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"[CloudSQLStateStore] SQLAlchemy State kaydetme hatası: {e}")
        finally:
            session.close()

    def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not self.SessionMaker:
            return None
        session = self.SessionMaker()
        try:
            record = session.query(SessionStateModel).filter_by(session_id=session_id).first()
            if record:
                return json.loads(record.state_data)
        except Exception as e:
            logger.error(f"[CloudSQLStateStore] SQLAlchemy State okuma hatası: {e}")
        finally:
            session.close()
        return None

# Alias for backward compatibility
LocalStateStore = CloudSQLStateStore


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """İki vektör arasındaki Cosine Similarity hesaplar."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


_EMBEDDING_MEM_CACHE: Dict[str, List[float]] = {}

def _get_embedding(text: str, api_key: str) -> Optional[List[float]]:
    """
    text-embedding-005 modeli ile metni 768 boyutlu vektöre dönüştürür.
    Türkçe semantik benzerliği (eş anlamlılar, anlam yakınlığı) yakalar.
    Mükerrer ağ isteklerini önlemek adına bellek içi önbelleği (in-memory dictionary cache) kullanır.
    """
    cache_key = text.strip().lower()
    if not cache_key:
        return None
    if cache_key in _EMBEDDING_MEM_CACHE:
        return _EMBEDDING_MEM_CACHE[cache_key]

    try:
        from api.modules.vertex_client import generate_embedding
        val = generate_embedding(text)
        if val and any(val):
            _EMBEDDING_MEM_CACHE[cache_key] = val
            return val
    except Exception as e:
        logger.debug(f"[Embedding] text-embedding-005 hatası, token overlap'e düşülüyor: {e}")
    return None

def get_text_embedding(text: str) -> Optional[List[float]]:
    """Genel text-embedding-005 vektörleştirme çağrısı (Vertex AI ADC veya API Key)."""
    return _get_embedding(text, "")


class LocalVectorStore:
    """
    Vertex AI Vector Search Emülatörü.
    Ticaret Bakanlığı BTB Kararlarını ve TGTC İzahnamelerini vektörleştirip
    dinamik olarak arar.

    Arama Stratejisi:
    - API key varsa → text-embedding-005 + Cosine Similarity (semantik)
    - Offline/test  → Jaccard Token Overlap (fallback)
    """
    def __init__(self, index_path: str = VECTOR_INDEX_PATH, btb_path: str = BTB_DB_PATH):
        self.index_path = index_path
        self.btb_path = btb_path
        self._docs_cache: Optional[List[Dict[str, Any]]] = None
        self._docs_cache_loaded_at: float = 0.0

    def _load_documents(self) -> List[Dict[str, Any]]:
        if self._docs_cache is not None and time.monotonic() - self._docs_cache_loaded_at < 900:
            return self._docs_cache

        # Öncelik: Zenginleştirilmiş Hiyerarşik Tarife Ağacı Kataloğu
        try:
            from api.db.tgtc_knowledge_base import load_btb_catalog
            catalog = load_btb_catalog()
            if catalog:
                self._docs_cache = catalog
                self._docs_cache_loaded_at = time.monotonic()
                logger.debug(f"[LocalVectorStore] Ana TGTC kütüphanesi başarıyla vektör deposuna yüklendi ({len(catalog)} kayıt).")
                return self._docs_cache
        except Exception as e:
            logger.warning(f"[LocalVectorStore] Ana TGTC kütüphanesi yükleme hatası: {e}")

        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._docs_cache = data.get("entries", [])
                    self._docs_cache_loaded_at = time.monotonic()
                    return self._docs_cache
            except Exception as e:
                logger.warning(f"[LocalVectorStore] Index okuma hatası: {e}")

        if os.path.exists(self.btb_path):
            try:
                with open(self.btb_path, "r", encoding="utf-8") as f:
                    self._docs_cache = json.load(f)
                    self._docs_cache_loaded_at = time.monotonic()
                    return self._docs_cache
            except Exception as e:
                logger.warning(f"[LocalVectorStore] BTB DB okuma hatası: {e}")

        return []

    def invalidate_cache(self):
        """Bellek içi döküman önbelleğini geçersiz kılar. Yeni kayıt eklendikten sonra çağrılır."""
        self._docs_cache = None
        self._docs_cache_loaded_at = 0.0
        logger.info("[LocalVectorStore] Döküman önbelleği temizlendi, bir sonraki aramada yeniden yüklenecek.")

    @staticmethod
    def _parse_publication_date(value: Any) -> Optional[datetime.date]:
        raw = str(value or "").strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(raw[:10], fmt).date()
            except ValueError:
                continue
        year_match = re.search(r"(?:19|20)\d{2}", raw)
        if year_match:
            return datetime.date(int(year_match.group(0)), 1, 1)
        return None

    def search_btb(
        self,
        query_text: str,
        allowed_chapters: Optional[List[str]] = None,
        top_k: int = 5,
        source_types: Optional[List[str]] = None,
        min_issue_date: Optional[datetime.date] = None,
    ) -> List[Dict[str, Any]]:
        return self.search_similar(
            query=query_text,
            top_k=top_k,
            allowed_chapters=allowed_chapters,
            source_types=source_types or ["BTB"],
            min_issue_date=min_issue_date,
        )

    def search_similar(
        self,
        query: str,
        top_k: int = 5,
        allowed_chapters: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        min_issue_date: Optional[datetime.date] = None,
    ) -> List[Dict[str, Any]]:
        docs = self._load_documents()
        if not docs:
            return []

        # --- Strateji 1: text-embedding-005 ile Cosine Similarity (Vertex AI ADC veya Key) ---
        # 1. Hızlı Aday Ön Süzgeci: İzinli fasıllar ve kelime örtüşmesi (O(N) CPU filtresi)
        today_iso = datetime.date.today().isoformat()
        query_tokens = set(query.lower().split())
        candidate_docs = []
        normalized_source_types = {str(s).upper() for s in (source_types or [])}
        for doc in docs:
            source_type = str(doc.get("source_type") or "BTB").upper()
            if normalized_source_types and source_type not in normalized_source_types:
                continue
            issue_date = self._parse_publication_date(doc.get("issue_date"))
            if min_issue_date and (issue_date is None or issue_date < min_issue_date):
                continue
            valid_until = str(doc.get("valid_until") or "")
            if valid_until and valid_until != "9999-12-31" and valid_until < today_iso:
                continue  # Versiyonlanmış eski mevzuat zırhı: Süresi biten kayıtlar atlanır
            chap = str(doc.get("chapter", doc.get("gtip_code", "")[:2])).zfill(2)
            if allowed_chapters and chap not in allowed_chapters:
                continue

            desc = doc.get("product_description", "")
            if not desc:
                continue

            doc_tokens = set(desc.lower().split())
            overlap = len(query_tokens.intersection(doc_tokens))
            candidate_docs.append((overlap, doc))

        if not candidate_docs:
            return []

        # En alakalı ilk 10 adayı derin semantik/vektör doğrulaması için seç (100+ gereksiz API çağrısını önler)
        candidate_docs.sort(key=lambda x: x[0], reverse=True)
        top_candidates = [d for _, d in candidate_docs[:10]]

        # --- Strateji 1: text-embedding-005 ile Cosine Similarity (Sadece Top-10 Aday) ---
        query_embedding = _get_embedding(query, "")
        if query_embedding and any(query_embedding):
            scored_results = []
            for doc in top_candidates:
                source_type = str(doc.get("source_type") or "BTB").upper()
                chap = str(doc.get("chapter", doc.get("gtip_code", "")[:2])).zfill(2)
                desc = doc.get("product_description", "")
                doc_embedding = doc.get("embedding") or _get_embedding(desc, "")
                if doc_embedding:
                    similarity = _cosine_similarity(query_embedding, doc_embedding)
                    scored_results.append({
                        "btb_no": doc.get("btb_no", "EMSAL-BTB"),
                        "gtip_code": doc.get("gtip_code"),
                        "chapter": chap,
                        "heading": doc.get("heading", doc.get("gtip_code", "")[:4]),
                        "issue_date": doc.get("issue_date", "2026-01-01"),
                        "product_description": doc.get("product_description"),
                        "legal_justification": doc.get("legal_justification"),
                        "source_type": source_type,
                        "source_url": doc.get("source_url"),
                        "similarity_score": round(similarity, 4)
                    })

            if scored_results:
                scored_results.sort(key=lambda x: x["similarity_score"], reverse=True)
                logger.info(f"[VectorStore] text-embedding-005 Cosine Similarity araması: {len(scored_results)} sonuç")
                return scored_results[:top_k]

        # --- Strateji 2: Jaccard Token Overlap (Offline Fallback) ---
        logger.debug("[VectorStore] Jaccard Token Overlap fallback kullanılıyor (API key yok veya embedding hatası).")
        scored_results = []
        for doc in top_candidates:
            chap = str(doc.get("chapter", doc.get("gtip_code", "")[:2])).zfill(2)
            desc = doc.get("product_description", "").lower()
            doc_tokens = set(desc.split())

            overlap = len(query_tokens.intersection(doc_tokens))
            union = len(query_tokens.union(doc_tokens)) or 1
            score = 0.5 + (overlap / union) * 0.45

            if overlap > 0 or not allowed_chapters:
                scored_results.append({
                    "btb_no": doc.get("btb_no", "EMSAL-BTB"),
                    "gtip_code": doc.get("gtip_code"),
                    "chapter": chap,
                    "heading": doc.get("heading", doc.get("gtip_code", "")[:4]),
                    "issue_date": doc.get("issue_date", "2026-01-01"),
                    "product_description": doc.get("product_description"),
                    "legal_justification": doc.get("legal_justification"),
                    "source_type": str(doc.get("source_type") or "BTB").upper(),
                    "source_url": doc.get("source_url"),
                    "similarity_score": round(score, 4)
                })

        scored_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored_results[:top_k]

local_state_store = LocalStateStore()
local_vector_store = LocalVectorStore()
