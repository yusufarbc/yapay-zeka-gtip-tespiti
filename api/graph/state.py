from typing import TypedDict, Optional, List, Dict, Any
from api.schemas.product import ProductFeatures, GTIPCandidate, HITLQuestion, PrecedentBTB

class GTIPState(TypedDict):
    session_id: str
    raw_text: str
    image_uri: Optional[str]
    masked_text: str
    pii_mapping: Dict[str, str]
    product_features: Optional[Dict[str, Any]]
    allowed_chapters: List[str]
    applied_gir_rules: List[str]
    candidates: List[Dict[str, Any]]
    selected_gtip: Optional[str]
    confidence_score: float
    is_compliant: bool
    conflict_reason: Optional[str]
    hitl_question: Optional[Dict[str, Any]]
    status: str # "COMPLETED" | "WAITING_FOR_USER" | "MANUAL_REVIEW_REQUIRED"
    legal_justification: Optional[str]
    precedents: List[Dict[str, Any]]
    audit_notes: List[str]

class CustomsState(TypedDict):
    """
    gcp_architecture_report.md Bölüm 6 Şartnamesi:
    LangGraph Etkileşimli GTİP Ajanı ve HITL Durum Makinesi Şeması.
    """
    session_id: str
    user_query: str
    product_specs: Dict[str, Any]
    candidate_heading: Optional[str]
    missing_parameter: Optional[str]
    question_payload: Optional[Dict[str, Any]]
    final_gtip: Optional[str]
    legal_basis: Optional[Dict[str, Any]]
    status: str # 'IN_PROGRESS' | 'WAITING_FOR_USER' | 'RESOLVED' | 'COMPLETED'
    audit_notes: List[str]
