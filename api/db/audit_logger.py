import json
import os
import logging
from typing import List, Optional
from datetime import datetime
from api.schemas.audit import AuditLogEntry

logger = logging.getLogger(__name__)


class FirestoreAuditLogger:
    """
    Modül 6: Audit Logging & Continuous Feedback Pipeline.
    Production: GCP Cloud Firestore `gtip_audit_logs` koleksiyonuna yazar.
    Geliştirme / emülatör: SQLite yedeğine düşer.
    """

    def __init__(self):
        self._firestore_client = None
        self._collection_name = "gtip_audit_logs"
        self._sqlite_fallback: Optional["_SQLiteAuditLogger"] = None
        self._init_backend()

    def _init_backend(self):
        from api.config import settings
        if settings.USE_GCP_EMULATOR:
            logger.info("[AuditLogger] Emülatör modu: SQLite backend kullanılıyor.")
            self._sqlite_fallback = _SQLiteAuditLogger()
            return
        try:
            from google.cloud import firestore
            self._firestore_client = firestore.Client(project=settings.GCP_PROJECT_ID)
            logger.info(f"[AuditLogger] Cloud Firestore bağlandı: proje={settings.GCP_PROJECT_ID}")
        except Exception as e:
            logger.warning(f"[AuditLogger] Firestore bağlantısı kurulamadı ({e}). SQLite'a düşülüyor.")
            self._sqlite_fallback = _SQLiteAuditLogger()

    def log_decision(self, entry: AuditLogEntry):
        if self._firestore_client:
            try:
                doc_ref = self._firestore_client.collection(self._collection_name).document(entry.session_id)
                doc_ref.set({
                    "session_id": entry.session_id,
                    "timestamp": entry.timestamp,
                    "user_email": entry.user_email,
                    "user_role": entry.user_role,
                    "product_name": entry.product_name,
                    "initial_gtip_proposed": entry.initial_gtip_proposed,
                    "final_gtip_approved": entry.final_gtip_approved,
                    "confidence_score": entry.confidence_score,
                    "is_hitl_triggered": entry.is_hitl_triggered,
                    "user_feedback": entry.user_feedback,
                    "execution_time_ms": entry.execution_time_ms,
                    # BigQuery / Looker Studio BI için türetilmiş alanlar
                    "chapter_code": entry.final_gtip_approved[:2] if entry.final_gtip_approved else None,
                    "heading_code": entry.final_gtip_approved[:4] if entry.final_gtip_approved else None,
                })
                logger.debug(f"[AuditLogger] Firestore'a kaydedildi: {entry.session_id}")
                return
            except Exception as e:
                logger.warning(f"[AuditLogger] Firestore yazma hatası ({e}). SQLite fallback'e düşülüyor.")
                if not self._sqlite_fallback:
                    self._sqlite_fallback = _SQLiteAuditLogger()
        if self._sqlite_fallback:
            self._sqlite_fallback.log_decision(entry)

    def get_all_logs(self, limit: int = 50) -> List[AuditLogEntry]:
        if self._firestore_client:
            try:
                docs = (
                    self._firestore_client.collection(self._collection_name)
                    .order_by("timestamp", direction="DESCENDING")
                    .limit(limit)
                    .stream()
                )
                entries = []
                for doc in docs:
                    d = doc.to_dict()
                    entries.append(AuditLogEntry(
                        session_id=d.get("session_id", ""),
                        timestamp=d.get("timestamp", ""),
                        user_email=d.get("user_email", ""),
                        user_role=d.get("user_role", ""),
                        product_name=d.get("product_name", ""),
                        initial_gtip_proposed=d.get("initial_gtip_proposed"),
                        final_gtip_approved=d.get("final_gtip_approved"),
                        confidence_score=d.get("confidence_score", 0.0),
                        is_hitl_triggered=bool(d.get("is_hitl_triggered", False)),
                        user_feedback=d.get("user_feedback"),
                        execution_time_ms=d.get("execution_time_ms", 0.0),
                    ))
                return entries
            except Exception as e:
                logger.warning(f"[AuditLogger] Firestore okuma hatası ({e}). SQLite fallback kullanılıyor.")
                if not self._sqlite_fallback:
                    self._sqlite_fallback = _SQLiteAuditLogger()
        if self._sqlite_fallback:
            return self._sqlite_fallback.get_all_logs(limit)
        return []

    def export_bigquery_payloads(self, limit: int = 100) -> List[dict]:
        """
        BigQuery `gtip_audit_logs` tablosuna aktarım ve Looker Studio BI görselleştirme payload'u üretir.
        """
        entries = self.get_all_logs(limit=limit)
        return [
            {
                "session_id": e.session_id,
                "timestamp": e.timestamp,
                "user_email": e.user_email,
                "user_role": e.user_role,
                "product_name": e.product_name,
                "chapter_code": e.final_gtip_approved[:2] if e.final_gtip_approved else None,
                "heading_code": e.final_gtip_approved[:4] if e.final_gtip_approved else None,
                "initial_gtip_proposed": e.initial_gtip_proposed,
                "final_gtip_approved": e.final_gtip_approved,
                "confidence_score": e.confidence_score,
                "is_hitl_triggered": e.is_hitl_triggered,
                "user_feedback": e.user_feedback,
                "execution_time_ms": e.execution_time_ms
            }
            for e in entries
        ]


class _SQLiteAuditLogger:
    """SQLite yedek backend — geliştirme ve Firestore erişimi yoksa kullanılır."""

    def __init__(self, db_path: str = None):
        import sqlite3 as _sqlite3
        self._sqlite3 = _sqlite3
        if db_path is None:
            if os.getenv("K_SERVICE") or not os.access(".", os.W_OK):
                db_path = "/tmp/audit_logs.db"
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                db_path = os.path.join(base_dir, "data", "audit_logs.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    session_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    user_email TEXT,
                    user_role TEXT,
                    product_name TEXT,
                    initial_gtip_proposed TEXT,
                    final_gtip_approved TEXT,
                    confidence_score REAL,
                    is_hitl_triggered INTEGER,
                    user_feedback TEXT,
                    execution_time_ms REAL
                )
            """)
            conn.commit()

    def log_decision(self, entry: AuditLogEntry):
        with self._sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO audit_logs (
                    session_id, timestamp, user_email, user_role, product_name,
                    initial_gtip_proposed, final_gtip_approved, confidence_score,
                    is_hitl_triggered, user_feedback, execution_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.session_id, entry.timestamp, entry.user_email, entry.user_role,
                entry.product_name, entry.initial_gtip_proposed, entry.final_gtip_approved,
                entry.confidence_score, 1 if entry.is_hitl_triggered else 0,
                entry.user_feedback, entry.execution_time_ms
            ))
            conn.commit()

    def get_all_logs(self, limit: int = 50) -> List[AuditLogEntry]:
        results = []
        with self._sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            for r in rows:
                results.append(AuditLogEntry(
                    session_id=r[0], timestamp=r[1], user_email=r[2], user_role=r[3],
                    product_name=r[4], initial_gtip_proposed=r[5], final_gtip_approved=r[6],
                    confidence_score=r[7], is_hitl_triggered=bool(r[8]),
                    user_feedback=r[9], execution_time_ms=r[10]
                ))
        return results


audit_logger = FirestoreAuditLogger()
