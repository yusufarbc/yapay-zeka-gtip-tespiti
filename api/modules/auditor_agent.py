from typing import List, Tuple, Optional
from api.schemas.product import ProductFeatures, GTIPCandidate, HITLQuestion, HITLOption

class AuditorAgent:
    """
    Modül 4: Cross-Validation & Auditor Agent (Çift Ajanlı Denetim Mimarisi).
    Proposer Agent'ın seçtiği GTİP kodunun resmi şartlarını okur, 
    ürün özellikleri ile tersine doğrulama yapar ve eksik/muğlak teknik veriler için dinamik soru üretir.
    """

    def audit_candidate(
        self, 
        candidate: GTIPCandidate, 
        features: ProductFeatures
    ) -> Tuple[float, bool, Optional[str], Optional[HITLQuestion]]:
        """
        Dinamik Çapraz Denetim Ve Belirsizlik Tespiti Yapar.
        Döndürür: (confidence_score, is_compliant, conflict_reason, hitl_question)
        """
        gtip = candidate.gtip_code
        confidence = candidate.score
        is_compliant = True
        conflict_reason = None
        hitl_question = None

        norm_name = features.product_name.lower()
        norm_mat = features.primary_material.lower()

        # 1. Genel Belirsizlik Kontrolü (Örn: "penye", "kumaş", "giyim" girilip hammadde belirtilmeyen durumlar)
        if ("penye" in norm_name or "kumaş" in norm_name or "giyim" in norm_name) and not features.composition_percentages:
            if "pamuk" not in norm_mat and "yün" not in norm_mat and "polyester" not in norm_mat and "deri" not in norm_mat:
                confidence = 0.70
                is_compliant = False
                hitl_question = HITLQuestion(
                    question_id="q_penye_material",
                    question_text=f"Sayın Müşavirim, girdiğiniz '{features.product_name}' ürününün lif bileşimi ve ham maddesi nedir?",
                    missing_parameter="primary_material",
                    options=[
                        HITLOption(
                            option_id="A",
                            text="%100 Pamuklu Penye Kumaş (Fasıl 52)",
                            impact_data={"primary_material": "Pamuk", "cotton": "1.0"}
                        ),
                        HITLOption(
                            option_id="B",
                            text="Yün / İnce Yapağı Dokuma (Fasıl 51)",
                            impact_data={"primary_material": "Yün", "wool": "1.0"}
                        ),
                        HITLOption(
                            option_id="C",
                            text="Sentetik / Polyester İplikli (Fasıl 55)",
                            impact_data={"primary_material": "Polyester", "polyester": "1.0"}
                        )
                    ]
                )
                return confidence, is_compliant, "Penye/Kumaş lif hammadde türü belirsiz.", hitl_question

        # 2. Kumaş Gramajı Kontrolü (Fasıl 52 / 55 / 61 / 62)
        if gtip.startswith(("5208", "5512", "6109", "6203")):
            if "weight" not in features.technical_specifications and not features.composition_percentages:
                confidence = 0.78
                is_compliant = False
                hitl_question = HITLQuestion(
                    question_id="q_fabric_spec",
                    question_text=f"Sayın Müşavirim, {features.product_name} ürününün m² gramajı ve kumaş bileşim oranı netleşmeli:",
                    missing_parameter="fabric_weight_composition",
                    options=[
                        HITLOption(
                            option_id="A",
                            text="130 gr/m² altında pamuk ağırlıklı kumaş",
                            impact_data={"fabric_weight": "under_130", "composition": "cotton"}
                        ),
                        HITLOption(
                            option_id="B",
                            text="130 gr/m² üstünde sentetik/karışım kumaş",
                            impact_data={"fabric_weight": "over_130", "composition": "synthetic"}
                        )
                    ]
                )
                return confidence, is_compliant, "Kumaş teknik özellikleri netleşmeli.", hitl_question

        # 3. Elektrikli Cihaz Güç / Motor Kontrolü (Fasıl 84 - 85)
        if gtip.startswith(("8418", "8509", "8517", "8471")):
            if "power_source" not in features.technical_specifications and "has_electric_motor" not in features.technical_specifications:
                confidence = 0.82
                is_compliant = False
                hitl_question = HITLQuestion(
                    question_id="q_power_check",
                    question_text=f"Sayın Müşavirim, {features.product_name} cihazının güç beslemesi ve çalışma kaynağını teyit ediniz:",
                    missing_parameter="power_source",
                    options=[
                        HITLOption(
                            option_id="A",
                            text="Dahili elektrik motorlu / bataryalı şarjlı cihaz",
                            impact_data={"has_electric_motor": "true", "power_source": "battery"}
                        ),
                        HITLOption(
                            option_id="B",
                            text="Harici şebeke elektriği / manuel çalışma",
                            impact_data={"has_electric_motor": "false", "power_source": "mains"}
                        )
                    ]
                )
                return confidence, is_compliant, "Cihaz çalışma ve güç kaynağı netleşmeli.", hitl_question

        # Tüm şartlar sağlandığında yüksek denetçi doğrulama puanı verilir
        return min(confidence + 0.15, 0.96), True, None, None

auditor_agent = AuditorAgent()
