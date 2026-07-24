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
