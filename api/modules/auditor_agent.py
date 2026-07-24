from typing import List, Tuple, Optional
from api.schemas.product import ProductFeatures, GTIPCandidate, HITLQuestion, HITLOption

class AuditorAgent:
    """
    Modül 4: Cross-Validation & Auditor Agent (Çift Ajanlı Denetim Mimarisi).
    Proposer Agent'ın seçtiği GTİP kodunun resmi şartlarını okur, 
    ürün özellikleri ile tersine doğrulama yapar.
    """

    def audit_candidate(
        self, 
        candidate: GTIPCandidate, 
        features: ProductFeatures
    ) -> Tuple[float, bool, Optional[str], Optional[HITLQuestion]]:
        """
        Denetim yapar. 
        Döndürür: (confidence_score, is_compliant, conflict_reason, hitl_question)
        """
        gtip = candidate.gtip_code
        confidence = candidate.score
        is_compliant = True
        conflict_reason = None
        hitl_question = None

        # 1. Kumaş Gramajı Kontrolü (Fasıl 52)
        if gtip.startswith("5208"):
            if "weight" not in features.technical_specifications:
                confidence = 0.75 # Güven %90 altına düşer
                is_compliant = False
                hitl_question = HITLQuestion(
                    question_id="q_fabric_weight",
                    question_text="Ahmet Bey, bu kumaşın metrekare ağırlığı 130 gramın altında mı yoksa üstünde mi?",
                    missing_parameter="fabric_weight",
                    options=[
                        HITLOption(
                            option_id="A",
                            text="130 gr/m² veya daha az (Hafif kumaş)",
                            impact_data={"fabric_weight": "under_130"}
                        ),
                        HITLOption(
                            option_id="B",
                            text="130 gr/m²'den fazla (Ağır kumaş)",
                            impact_data={"fabric_weight": "over_130"}
                        )
                    ]
                )
                return confidence, is_compliant, "Kumaş metrekare gramajı eksik.", hitl_question

        # 2. Elektrik Motor Gücü / Tipi Kontrolü (Fasıl 8509 / Ev Aleti)
        if gtip.startswith("8509"):
            if "has_electric_motor" not in features.technical_specifications:
                confidence = 0.80
                is_compliant = False
                hitl_question = HITLQuestion(
                    question_id="q_motor_check",
                    question_text="Cihazın içerisinde kendinden bir elektrik motoru bulunuyor mu?",
                    missing_parameter="has_electric_motor",
                    options=[
                        HITLOption(
                            option_id="A",
                            text="Evet, dahili elektrik motorludur.",
                            impact_data={"has_electric_motor": "true"}
                        ),
                        HITLOption(
                            option_id="B",
                            text="Hayır, manuel veya motorsuzdur.",
                            impact_data={"has_electric_motor": "false"}
                        )
                    ]
                )
                return confidence, is_compliant, "Elektrik motor varlığı belirsiz.", hitl_question

        # Şartlar uyuyorsa yüksek güven skoru
        return min(confidence + 0.15, 0.96), True, None, None

auditor_agent = AuditorAgent()
