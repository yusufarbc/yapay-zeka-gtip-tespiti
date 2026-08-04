from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class PredicateStatus(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"

class FactStatus(str, Enum):
    EXPLICIT = "EXPLICIT"
    INFERRED = "INFERRED"
    MISSING = "MISSING"

class LegalPredicate(BaseModel):
    predicate_id: str = Field(..., description="Tekil kural kimliği (ör: P_8542_1)")
    description: str = Field(..., description="Doğrulanacak yasal/teknik koşul açıklaması")
    required_value: str = Field(..., description="Beklenen yasal değer (TRUE/FALSE)")
    statute_reference: str = Field(..., description="TGTC İzahnamesi veya GİR kural referansı")

class PredicateVerificationResult(BaseModel):
    predicate_id: str
    description: str
    status: PredicateStatus
    evidence_quote: Optional[str] = None
    statute_reference: str

class ProductFact(BaseModel):
    feature_name: str
    value: Optional[Any] = None
    status: FactStatus = FactStatus.EXPLICIT
