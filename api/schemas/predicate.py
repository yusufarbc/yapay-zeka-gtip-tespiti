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
    required_value: PredicateStatus = PredicateStatus.TRUE
    evidence_quote: Optional[str] = None
    statute_reference: str

class ProductFact(BaseModel):
    feature_name: str
    value: Optional[Any] = None
    status: FactStatus = FactStatus.EXPLICIT

class TariffVerification(BaseModel):
    """
    Pydantic Structured Output Model for LLM GTİP Verification.
    Yapay zekanın serbest metin yerine katı şema ile doğrulama yapmasını sağlar.
    """
    candidate_gtip: str = Field(description="Doğrulanan 12 veya 4 haneli GTİP kodu")
    is_material_compliant: bool = Field(description="Ürünün ana malzemesi bu pozisyonla yasal olarak uyumlu mu?")
    is_function_compliant: bool = Field(description="Ürünün işlevi ve kullanım amacı bu pozisyona uygun mu?")
    exclusion_notes_violated: bool = Field(description="İlgili fasıl veya pozisyon dışlama notları ihlal edildi mi? (True ise ürün bu pozisyona GİREMEZ)")
    gir_rule_applied: str = Field(default="GIR 1", description="Uygulanan GİR Yorum Kuralı (örn: GIR 1, GIR 3(b))")
    legal_reasoning_points: List[str] = Field(default_factory=list, description="Yasal gerekçe maddeleri")
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Modelin yasal şartlara uygunluk güven puanı (0.0 - 1.0)")

class ChapterExclusionCheck(BaseModel):
    """
    Fasıl Dışlama Notu Değerlendirme Sonucu (Adım 2 Exclusion Check).
    """
    chapter_code: str = Field(description="2 haneli Fasıl Kodu (örn: 64, 85)")
    is_excluded: bool = Field(description="Ürün bu faslın dışlama notlarına takılarak elendi mi?")
    violated_exclusion_note: Optional[str] = Field(default=None, description="İhlal edilen dışlama hükmü")
    recommended_alternative_chapter: Optional[str] = Field(default=None, description="Yönlendirilen alternatif fasıl")
