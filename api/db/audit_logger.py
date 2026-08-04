import json
import sqlite3
import os
from typing import List
from datetime import datetime
from api.schemas.audit import AuditLogEntry

class AuditLogger:
    """
    Modül 6: Audit Logging & Continuous Feedback Pipeline.
    Tüm analiz oturumu kararlarını ve insan onaylarını SQLite / BigQuery üzerine kaydeder.
    """

    def __init__(self, db_path: str = None):
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO audit_logs (
                    session_id, timestamp, user_email, user_role, product_name,
                    initial_gtip_proposed, final_gtip_approved, confidence_score,
                    is_hitl_triggered, user_feedback, execution_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.session_id,
                entry.timestamp,
                entry.user_email,
                entry.user_role,
                entry.product_name,
                entry.initial_gtip_proposed,
                entry.final_gtip_approved,
                entry.confidence_score,
                1 if entry.is_hitl_triggered else 0,
                entry.user_feedback,
                entry.execution_time_ms
            ))
            conn.commit()

    def get_all_logs(self, limit: int = 50) -> List[AuditLogEntry]:
        results = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            for r in rows:
                results.append(AuditLogEntry(
                    session_id=r[0],
                    timestamp=r[1],
                    user_email=r[2],
                    user_role=r[3],
                    product_name=r[4],
                    initial_gtip_proposed=r[5],
                    final_gtip_approved=r[6],
                    confidence_score=r[7],
                    is_hitl_triggered=bool(r[8]),
                    user_feedback=r[9],
                    execution_time_ms=r[10]
                ))
        return results

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

audit_logger = AuditLogger()
