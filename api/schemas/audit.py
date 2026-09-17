from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone

class AuditLogEntry(BaseModel):
    session_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_email: str
    user_role: str
    product_name: str
    initial_gtip_proposed: Optional[str] = None
    final_gtip_approved: str
    confidence_score: float
    is_hitl_triggered: bool
    user_feedback: Optional[str] = None
    execution_time_ms: float

class AuditLogQueryResponse(BaseModel):
    total_count: int
    entries: List[AuditLogEntry]
