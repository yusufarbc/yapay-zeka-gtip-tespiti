from pydantic import BaseModel, Field
from typing import Optional, Dict, List

class ProductFeatures(BaseModel):
    product_name: str = Field(description="Ürünün ticari adı veya kısa tanımı")
    primary_material: str = Field(description="Baskın malzeme: Pamuk, Plastik, Çelik, Cam vb.")
    composition_percentages: Optional[Dict[str, float]] = Field(
        default=None, 
        description="Karışım oranları: örn. {'cotton': 0.60, 'polyester': 0.40}"
    )
    intended_use: str = Field(description="Kullanım amacı: Oyuncak, Kişisel Bakım, Ev Aleti, Sanayi vb.")
    is_set_or_kit: bool = Field(default=False, description="Ürün bir takım/set halinde mi satılıyor?")
    is_disassembled: bool = Field(default=False, description="Ürün demonte/sökülmüş halde mi?")
    technical_specifications: Dict[str, str] = Field(
        default_factory=dict, 
        description="Voltaj, motor gücü, gramaj, frekans aralığı vb. teknik detaylar"
    )

class PrecedentBTB(BaseModel):
    btb_no: str = Field(description="Ticaret Bakanlığı BTB Karar Numarası")
    gtip_code: str = Field(description="BTB kararı ile verilen 12 haneli GTİP Kodu")
    issue_date: str = Field(description="BTB Karar Tarihi")
    product_description: str = Field(description="BTB kararındaki ürün tanımı")
    legal_justification: str = Field(description="Bakanlığın yasal gerekçe açıklaması")
    similarity_score: float = Field(description="Vektör benzerlik skoru (0.0 - 1.0)")

class GTIPCandidate(BaseModel):
    gtip_code: str = Field(description="12 Haneli GTİP Kodu (örn. 8471.30.00.00.11)")
    description: str = Field(description="TGTC Resmi Pozisyon Tanımı")
    chapter: str = Field(description="2 Haneli Fasıl Kodu")
    heading: str = Field(description="4 Haneli Pozisyon Kodu")
    score: float = Field(description="Kombine RAG Skoru (BTB + TGTC)")
    precedents: List[PrecedentBTB] = Field(default_factory=list)

class HITLOption(BaseModel):
    option_id: str = Field(description="Seçenek Kimliği (A, B, C)")
    text: str = Field(description="Seçenek Açıklaması")
    impact_data: Dict[str, str] = Field(default_factory=dict, description="State güncelleyecek teknik veri")

class HITLQuestion(BaseModel):
    question_id: str
    question_text: str = Field(description="Gümrük Müşavirine yöneltilen netleştirici teknik soru")
    missing_parameter: str = Field(description="Aranan eksik parametre adı (örn. grammage, motor_power)")
    options: List[HITLOption]

class HITLResponse(BaseModel):
    session_id: str
    question_id: str
    selected_option_id: str
    custom_note: Optional[str] = None

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
    hitl_question: Optional[HITLQuestion] = None
    audit_notes: List[str] = Field(default_factory=list)
