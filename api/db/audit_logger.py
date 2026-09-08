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
        self._sqlalchemy_fallback: Optional["_SQLAlchemyAuditLogger"] = None
        self._init_backend()

    def _init_backend(self):
        from api.config import settings
        if settings.USE_GCP_EMULATOR or settings.AUDIT_BACKEND == "cloudsql":
            logger.info("[AuditLogger] SQLAlchemy ORM backend kullanılıyor.")
            self._sqlalchemy_fallback = _SQLAlchemyAuditLogger()
            return
        try:
            from google.cloud import firestore
            self._firestore_client = firestore.Client(project=settings.GCP_PROJECT_ID)
            logger.info(f"[AuditLogger] Cloud Firestore bağlandı: proje={settings.GCP_PROJECT_ID}")
        except Exception as e:
            logger.warning(f"[AuditLogger] Firestore bağlantısı kurulamadı ({e}). GCP Cloud SQL (SQLAlchemy ORM)'e düşülüyor.")
            self._sqlalchemy_fallback = _SQLAlchemyAuditLogger()

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
                logger.warning(f"[AuditLogger] Firestore yazma hatası ({e}). SQLAlchemy ORM fallback'e düşülüyor.")
                if not self._sqlalchemy_fallback:
                    self._sqlalchemy_fallback = _SQLAlchemyAuditLogger()
        if self._sqlalchemy_fallback:
            self._sqlalchemy_fallback.log_decision(entry)

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
                logger.warning(f"[AuditLogger] Firestore okuma hatası ({e}). SQLAlchemy ORM fallback kullanılıyor.")
                if not self._sqlalchemy_fallback:
                    self._sqlalchemy_fallback = _SQLAlchemyAuditLogger()
        if self._sqlalchemy_fallback:
            return self._sqlalchemy_fallback.get_all_logs(limit)
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


from api.db.database import SessionLocal, AuditLogModel, engine, Base

class _SQLAlchemyAuditLogger:
    """GCP Cloud SQL PostgreSQL SQLAlchemy ORM Audit Logger."""

    def __init__(self):
        try:
            Base.metadata.create_all(bind=engine)
        except Exception as e:
            logger.warning(f"[AuditLogger] ORM Tablo init uyarısı: {e}")

    def log_decision(self, entry: AuditLogEntry):
        session = SessionLocal()
        try:
            record = session.query(AuditLogModel).filter_by(session_id=entry.session_id).first()
            if record:
                record.timestamp = entry.timestamp
                record.user_email = entry.user_email
                record.user_role = entry.user_role
                record.product_name = entry.product_name
                record.initial_gtip_proposed = entry.initial_gtip_proposed
                record.final_gtip_approved = entry.final_gtip_approved
                record.confidence_score = entry.confidence_score
                record.is_hitl_triggered = entry.is_hitl_triggered
                record.user_feedback = entry.user_feedback
                record.execution_time_ms = entry.execution_time_ms
            else:
                record = AuditLogModel(
                    session_id=entry.session_id,
                    timestamp=entry.timestamp,
                    user_email=entry.user_email,
                    user_role=entry.user_role,
                    product_name=entry.product_name,
                    initial_gtip_proposed=entry.initial_gtip_proposed,
                    final_gtip_approved=entry.final_gtip_approved,
                    confidence_score=entry.confidence_score,
                    is_hitl_triggered=entry.is_hitl_triggered,
                    user_feedback=entry.user_feedback,
                    execution_time_ms=entry.execution_time_ms
                )
                session.add(record)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"[AuditLogger] SQLAlchemy log_decision hatası: {e}")
        finally:
            session.close()

    def get_all_logs(self, limit: int = 50) -> List[AuditLogEntry]:
        results = []
        session = SessionLocal()
        try:
            records = session.query(AuditLogModel).order_by(AuditLogModel.created_at.desc()).limit(limit).all()
            for r in records:
                results.append(AuditLogEntry(
                    session_id=r.session_id,
                    timestamp=r.timestamp or "",
                    user_email=r.user_email or "",
                    user_role=r.user_role or "",
                    product_name=r.product_name or "",
                    initial_gtip_proposed=r.initial_gtip_proposed or "",
                    final_gtip_approved=r.final_gtip_approved or "",
                    confidence_score=r.confidence_score or 0.0,
                    is_hitl_triggered=bool(r.is_hitl_triggered),
                    user_feedback=r.user_feedback or "",
                    execution_time_ms=r.execution_time_ms or 0.0
                ))
        except Exception as e:
            logger.error(f"[AuditLogger] SQLAlchemy get_all_logs hatası: {e}")
        finally:
            session.close()
        return results


audit_logger = FirestoreAuditLogger()
