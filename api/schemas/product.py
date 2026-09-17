from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List, Any


class LegalSource(BaseModel):
    """GTİP kararında gerçekten sorgulanan ve kullanıcıya gösterilebilen hukuki kaynak."""
    source_type: str = Field(
        description="TGTC_2026 | GIR | FASIL_NOTU | IZAHNAME | BTB | SINIFLANDIRMA_KARARI | GUMRUK_MEVZUATI",
        max_length=50,
    )
    reference_no: str = Field(default="", max_length=150)
    title: str = Field(default="", max_length=500)
    publication_date: Optional[str] = Field(default=None, max_length=30)
    excerpt: str = Field(default="")
    source_url: Optional[str] = None
    legal_role: str = Field(
        default="CONTEXT",
        description="NORMATIVE | INTERPRETIVE | INDIVIDUAL_PRECEDENT | CONTEXT",
        max_length=40,
    )
    authority_level: int = Field(
        default=9,
        ge=1,
        le=9,
        description="1=TGTC/GYK/yasal not, 2=tebliğ, 3=kişiye özgü BTB, 4+=yorum/emsal",
    )
    effective_from: Optional[str] = Field(default=None, max_length=30)
    effective_to: Optional[str] = Field(default=None, max_length=30)
    is_binding: bool = Field(
        default=False,
        description="Kaynağın bu ürün/sorgu için bağlayıcı olup olmadığı; başka kişilerin BTB'si false olmalıdır.",
    )

    @field_validator("source_type", mode="before")
    @classmethod
    def normalize_source_type(cls, value):
        return str(value or "").strip().upper()[:50]

    @field_validator("reference_no", mode="before")
    @classmethod
    def bound_reference_no(cls, value):
        return str(value or "").strip()[:150]

    @field_validator("title", mode="before")
    @classmethod
    def bound_title(cls, value):
        # Dış kaynak başlıkları/ürün tanımları şema sınırını aşsa bile bütün
        # analizi 500'e düşürmemeli. Tam metin excerpt alanında korunur.
        return str(value or "").strip()[:500]

    @field_validator("publication_date", mode="before")
    @classmethod
    def bound_publication_date(cls, value):
        if value is None:
            return None
        return str(value).strip()[:30]

class ProductFeatures(BaseModel):
    product_name: str = Field(description="Ürünün ticari adı veya kısa tanımı", min_length=1, max_length=2000)
    commercial_name: Optional[str] = Field(default=None, description="Ticari eşya adı / marka modeli", max_length=1000)
    primary_material: str = Field(description="Baskın malzeme: Pamuk, Plastik, Çelik, Cam vb.", max_length=500)
    function: Optional[str] = Field(default=None, description="Eşyanın temel fonksiyonu / işlevi", max_length=1000)
    accessories_or_packaging: Optional[str] = Field(default=None, description="Birlikte verilen ambalaj, kılıf, kutu veya aksesuarlar", max_length=1000)
    composition_percentages: Optional[Dict[str, float]] = Field(
        default=None, 
        description="Karışım oranları: örn. {'cotton': 0.60, 'polyester': 0.40}"
    )
    intended_use: str = Field(description="Kullanım amacı: Oyuncak, Kişisel Bakım, Ev Aleti, Sanayi vb.", max_length=1000)
    is_set_or_kit: bool = Field(default=False, description="Ürün bir takım/set halinde mi satılıyor?")
    is_disassembled: bool = Field(default=False, description="Ürün demonte/sökülmüş halde mi?")
    technical_specifications: Dict[str, str] = Field(
        default_factory=dict, 
        description="Voltaj, motor gücü, gramaj, frekans aralığı vb. teknik detaylar"
    )

class PrecedentBTB(BaseModel):
    btb_no: str = Field(default="", description="Ticaret Bakanlığı BTB Karar Numarası", max_length=100)
    gtip_code: str = Field(default="", description="BTB kararı ile verilen 12 haneli GTİP Kodu", max_length=30)
    issue_date: str = Field(default="", description="BTB Karar Tarihi", max_length=20)
    product_description: str = Field(description="BTB kararındaki ürün tanımı")
    legal_justification: str = Field(description="Bakanlığın yasal gerekçe açıklaması")
    similarity_score: float = Field(description="Vektör benzerlik skoru (0.0 - 1.0)", ge=0.0, le=1.0)
    source_type: str = Field(default="BTB", max_length=50)
    source_url: Optional[str] = None


class PrecedentEBTI(BaseModel):
    reference_no: str
    country: str
    cn_code: str = Field(pattern=r"^\d{8}$")
    issue_date: str
    valid_until: Optional[str] = None
    product_description: str
    legal_justification: str = ""
    legal_justification_tr: Optional[str] = None
    language: str = "en"
    similarity_score: float = Field(ge=0.0, le=1.0)
    source_url: str
    image_url: Optional[str] = None

class GTIPCandidate(BaseModel):
    gtip_code: str = Field(description="12 Haneli GTİP Kodu (örn. 8471.30.00.00.11)", max_length=30)
    description: str = Field(description="TGTC Resmi Pozisyon Tanımı")
    chapter: str = Field(description="2 Haneli Fasıl Kodu", max_length=5)
    heading: str = Field(description="4 Haneli Pozisyon Kodu", max_length=10)
    score: float = Field(description="Kombine RAG Skoru (BTB + TGTC)", ge=0.0, le=1.0)
    precedents: List[PrecedentBTB] = Field(default_factory=list)
    legal_sources: List[LegalSource] = Field(default_factory=list)
    consulted_sources: List[str] = Field(default_factory=list)

class HITLOption(BaseModel):
    option_id: str = Field(description="Seçenek Kimliği (A, B, C)", max_length=50)
    text: str = Field(description="Seçenek Açıklaması", max_length=500)
    impact_data: Dict[str, str] = Field(default_factory=dict, description="State güncelleyecek teknik veri")

class HITLQuestion(BaseModel):
    question_id: str = Field(max_length=100)
    question_text: str = Field(description="Gümrük Müşavirine yöneltilen netleştirici teknik soru", max_length=1000)
    missing_parameter: str = Field(description="Aranan eksik parametre adı (örn. grammage, motor_power)", max_length=100)
    options: List[HITLOption]

class HITLResponse(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    question_id: str = Field(min_length=1, max_length=100)
    selected_option_id: str = Field(min_length=1, max_length=50)
    custom_note: Optional[str] = Field(default=None, max_length=2000)

class GTIPDecision(BaseModel):
    session_id: str
    status: str = Field(description="COMPLETED | WAITING_FOR_USER | MANUAL_REVIEW_REQUIRED")
    gtip_code: Optional[str] = None
    confidence_score: float = 0.0
    official_statute_text: Optional[str] = Field(default=None, description="Veritabanından kural tabanlı olarak çekilen Orijinal Resmi Mevzuat ve İzahname Maddesi")
    llm_reasoning_commentary: Optional[str] = Field(default=None, description="Yapay zeka modelinin seçime dair ayrı sunduğu değerlendirme ve gerekçe yorumu")
    legal_justification: Optional[str] = None
    applied_gir_rules: List[str] = Field(default_factory=list)
    precedent_btbs: List[PrecedentBTB] = Field(default_factory=list)
    precedent_ebtis: List[PrecedentEBTI] = Field(default_factory=list)
    legal_sources: List[LegalSource] = Field(default_factory=list)
    consulted_sources: List[str] = Field(default_factory=list)
    hitl_question: Optional[HITLQuestion] = None
    audit_notes: List[str] = Field(default_factory=list)
    trade_measures: Optional[Dict[str, Any]] = Field(default=None, description="İGV, TAREKS, KDV, Gözetim vb. tedbir kartları")
    state_machine_stage: Optional[str] = Field(default=None, description="FSM Durumu (DURUM_0 - DURUM_6)")
    guardrail_status: Optional[str] = Field(default=None, description="VERIFIED_LEAF | FALLBACK_SUBHEADING | STRICT_CHECK_PASSED")
    tariff_year: str = Field(default="2026", max_length=10)
    legal_validation_status: Optional[str] = Field(
        default=None,
        description="PASSED | MISSING_NORMATIVE_EVIDENCE | EXPIRED_EVIDENCE | MANUAL_REVIEW",
    )
