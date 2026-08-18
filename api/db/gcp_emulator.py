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
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.embed_content(
            model="text-embedding-005",
            contents=text,
            config={"task_type": "RETRIEVAL_QUERY"}
        )
        # google-genai SDK yapısına göre değer erişimi
        if hasattr(response, "embeddings") and response.embeddings:
            val = response.embeddings[0].values
            _EMBEDDING_MEM_CACHE[cache_key] = val
            return val
        if hasattr(response, "embedding") and response.embedding:
            val = response.embedding.values
            _EMBEDDING_MEM_CACHE[cache_key] = val
            return val
    except Exception as e:
        logger.debug(f"[Embedding] text-embedding-005 hatası, token overlap'e düşülüyor: {e}")
    return None


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

    def _load_documents(self) -> List[Dict[str, Any]]:
        if self._docs_cache is not None:
            return self._docs_cache

        # Öncelik: Zenginleştirilmiş Hiyerarşik Tarife Ağacı Kataloğu
        try:
            from api.db.tgtc_knowledge_base import load_btb_catalog
            catalog = load_btb_catalog()
            if catalog:
                self._docs_cache = catalog
                logger.debug(f"[LocalVectorStore] Ana TGTC kütüphanesi başarıyla vektör deposuna yüklendi ({len(catalog)} kayıt).")
                return self._docs_cache
        except Exception as e:
            logger.warning(f"[LocalVectorStore] Ana TGTC kütüphanesi yükleme hatası: {e}")

        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._docs_cache = data.get("entries", [])
                    return self._docs_cache
            except Exception as e:
                logger.warning(f"[LocalVectorStore] Index okuma hatası: {e}")

        if os.path.exists(self.btb_path):
            try:
                with open(self.btb_path, "r", encoding="utf-8") as f:
                    self._docs_cache = json.load(f)
                    return self._docs_cache
            except Exception as e:
                logger.warning(f"[LocalVectorStore] BTB DB okuma hatası: {e}")

        return []

    def invalidate_cache(self):
        """Bellek içi döküman önbelleğini geçersiz kılar. Yeni kayıt eklendikten sonra çağrılır."""
        self._docs_cache = None
        logger.info("[LocalVectorStore] Döküman önbelleği temizlendi, bir sonraki aramada yeniden yüklenecek.")

    def search_btb(self, query_text: str, allowed_chapters: Optional[List[str]] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        return self.search_similar(query=query_text, top_k=top_k, allowed_chapters=allowed_chapters)

    def search_similar(self, query: str, top_k: int = 5, allowed_chapters: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        docs = self._load_documents()
        if not docs:
            return []

        api_key = os.getenv("GEMINI_API_KEY", "")

        # --- Strateji 1: text-embedding-005 ile Cosine Similarity ---
        if api_key:
            query_embedding = _get_embedding(query, api_key)
            if query_embedding:
                scored_results = []
                for doc in docs:
                    valid_until = str(doc.get("valid_until") or "")
                    if valid_until and valid_until != "9999-12-31" and valid_until < "2026-01-01":
                        continue  # Versiyonlanmış eski mevzuat zırhı: Süresi biten kayıtlar atlanır
                    chap = str(doc.get("chapter", doc.get("gtip_code", "")[:2])).zfill(2)
                    if allowed_chapters and chap not in allowed_chapters:
                        continue

                    desc = doc.get("product_description", "")
                    if not desc:
                        continue

                    doc_embedding = _get_embedding(desc, api_key)
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
                            "similarity_score": round(similarity, 4)
                        })

                if scored_results:
                    scored_results.sort(key=lambda x: x["similarity_score"], reverse=True)
                    logger.info(f"[VectorStore] text-embedding-005 Cosine Similarity araması: {len(scored_results)} sonuç")
                    return scored_results[:top_k]

        # --- Strateji 2: Jaccard Token Overlap (Offline Fallback) ---
        logger.debug("[VectorStore] Jaccard Token Overlap fallback kullanılıyor (API key yok veya embedding hatası).")
        query_tokens = set(query.lower().split())
        scored_results = []

        for doc in docs:
            valid_until = str(doc.get("valid_until") or "")
            if valid_until and valid_until != "9999-12-31" and valid_until < "2026-01-01":
                continue  # Versiyonlanmış eski mevzuat zırhı
            chap = str(doc.get("chapter", doc.get("gtip_code", "")[:2])).zfill(2)
            if allowed_chapters and chap not in allowed_chapters:
                continue

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
                    "similarity_score": round(score, 4)
                })

        scored_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored_results[:top_k]

local_state_store = LocalStateStore()
local_vector_store = LocalVectorStore()
