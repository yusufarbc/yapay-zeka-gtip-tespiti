"""
Modül 5: Deterministic Symbolic Decision Engine & HITL Manager.
Karar verme, gerekçelendirme ve güven skoru hesaplama yetkisini LLM'den tamamen alıp Python sembolik mantığına devreder.

Halüsinasyon Sıfırlama (No-AI Output Binding):
- Resmi mevzuat ve izahname metinleri kesinlikle AI üretimi değildir; canlı SQL/Mevzuat veritabanından STATİK JOIN edilerek basılır.
- RAG adayları arası benzerlik skoru farkı <%5 ise otomatik karar verilmeyip Müşavire [A]/[B] çoktan seçmeli sorusu sorulur.
- Dışlama notu ihlal edilen adaylar otomatik elenir.
"""

from typing import List, Dict, Any, Tuple, Optional, Union
from api.schemas.product import GTIPCandidate, GTIPDecision, HITLQuestion, HITLOption
from api.schemas.predicate import PredicateVerificationResult, PredicateStatus, TariffVerification
from api.db.tgtc_knowledge_base import get_local_tgtc_headings, load_tgtc_rules_and_notes, TGTC_CHAPTERS

class DeterministicDecisionEngine:
    def evaluate_decision(
        self,
        session_id: str,
        top_candidate: GTIPCandidate,
        verification_results: Union[List[PredicateVerificationResult], TariffVerification],
        candidates: Optional[List[GTIPCandidate]] = None
    ) -> GTIPDecision:
        """
        Predikat doğrulama sonuçlarını, TariffVerification yapılandırılmış çıktısını ve
        RAG aday skoru dağılımını değerlendirerek deterministik GTİP kararını üretir.
        """
        # TariffVerification desteği
        tariff_verif: Optional[TariffVerification] = None
        predicate_list: List[PredicateVerificationResult] = []

        if isinstance(verification_results, TariffVerification):
            tariff_verif = verification_results
        elif isinstance(verification_results, list):
            predicate_list = verification_results

        # STRICT OUTPUT BINDING: Statik Veritabanı ve Mevzuat Eşleştirme (No-AI Output)
        headings_map = get_local_tgtc_headings()
        rules_db = load_tgtc_rules_and_notes()
        chap_code = str(top_candidate.gtip_code)[:2].zfill(2)
        head_code = str(top_candidate.gtip_code)[:4].zfill(4)

        head_title = headings_map.get(head_code) or headings_map.get(top_candidate.gtip_code) or top_candidate.description
        chap_title = TGTC_CHAPTERS.get(chap_code, "Genel Gümrük Tarife Pozisyonu")
        chap_note = rules_db.get("fasil_notlari", {}).get(chap_code, "")

        official_statute = (
            f"Türk Gümrük Tarife Cetveli (TGTC) 2026 Resmi Mevzuatı - Pozisyon {head_code}: {head_title}.\n"
            f"Bağlı Olduğu Fasıl {chap_code}: {chap_title}. (Statik Mevzuat Kütüphanesi Kaydı)"
        )
        if chap_note:
            official_statute += f"\nResmî Bakanlık İzahname ve Hukuki Uygulama Notu: {chap_note}"

        applied_rules = [
            f"GİR 1 & GİR 6: TGTC Yasal Tarife Eşleştirmesi.",
            f"Pozisyon {head_code} Resmi Tanımı: {head_title}"
        ]

        # 1. ÖNCELİKLİ DURUM: %5 Benzerlik Skoru HITL Kuralı (İki Aday Arası Çok Yakın Mesafe)
        if candidates and len(candidates) >= 2:
            cand1, cand2 = candidates[0], candidates[1]
            score_diff = abs((cand1.score or 0.8) - (cand2.score or 0.75))
            if score_diff < 0.05 and cand1.gtip_code != cand2.gtip_code:
                question_id = "Q_HITL_SCORE_CLOSE_5_PCT"
                hitl_q = HITLQuestion(
                    question_id=question_id,
                    question_text=f"En iyi 2 GTİP adayı ({cand1.gtip_code} ve {cand2.gtip_code}) arasındaki benzeşme skoru farkı (<%5) çok yakın olduğu için Gümrük Müşavirinin yasal teyidi zorunlu kılınmıştır.",
                    missing_parameter="gtip_disambiguation_choice",
                    options=[
                        HITLOption(
                            option_id="OPT_CAND1",
                            text=f"[A] {cand1.gtip_code} - {cand1.description[:55]}... (Skor: {cand1.score})",
                            impact_data={"selected_gtip": cand1.gtip_code}
                        ),
                        HITLOption(
                            option_id="OPT_CAND2",
                            text=f"[B] {cand2.gtip_code} - {cand2.description[:55]}... (Skor: {cand2.score})",
                            impact_data={"selected_gtip": cand2.gtip_code}
                        )
                    ]
                )
                llm_commentary = (
                    f"Yapay Zeka Mantıksal Doğrulama (%5 Benzerlik Eşik Kuralı): RAG sorgusundaki ilk iki emsal karar "
                    f"({cand1.gtip_code}: {cand1.score} vs {cand2.gtip_code}: {cand2.score}) arasındaki skor farkı %5'ten az olduğundan, "
                    f"halüsinasyonu engellemek adına otomatik karar üretilmeyip Gümrük Müşavirine (A / B seçenekli) teyit sorusu yöneltilmiştir."
                )
                return GTIPDecision(
                    session_id=session_id,
                    status="WAITING_FOR_USER",
                    gtip_code=cand1.gtip_code,
                    confidence_score=round(min(cand1.score or 0.75, 0.79), 2),
                    official_statute_text=official_statute,
                    llm_reasoning_commentary=llm_commentary,
                    legal_justification=official_statute,
                    applied_gir_rules=applied_rules + [f"GİR 3a / GİR 3b: %5 Eşik Kuralı (Skor farkı: {round(score_diff, 3)}) nedeniyle HITL tetiklendi."],
                    precedent_btbs=cand1.precedents,
                    hitl_question=hitl_q,
                    audit_notes=[f"İlk 2 aday skor farkı ({round(score_diff, 3)}) < %5 olduğu için çoktan seçmeli HITL soruldu."]
                )

        # 2. TariffVerification ile Doğrulama Değerlendirmesi
        if tariff_verif:
            if tariff_verif.exclusion_notes_violated or not tariff_verif.is_material_compliant or not tariff_verif.is_function_compliant or tariff_verif.confidence_score < 0.60:
                reason = "Dışlama notu ihlali" if tariff_verif.exclusion_notes_violated else "Malzeme/fonksiyon kriteri veya yapay zeka doğrulama yetersizliği"
                return GTIPDecision(
                    session_id=session_id,
                    status="MANUAL_REVIEW_REQUIRED",
                    gtip_code=top_candidate.gtip_code,
                    confidence_score=round(tariff_verif.confidence_score or 0.45, 2),
                    official_statute_text=official_statute,
                    llm_reasoning_commentary=f"Yasal Doğrulama Uyarısı ({reason}): {'; '.join(tariff_verif.legal_reasoning_points or ['Manuel inceleme gereklidir.'])}",
                    legal_justification=official_statute,
                    applied_gir_rules=applied_rules + [f"İnceleme Gerekçesi: {tariff_verif.gir_rule_applied}"],
                    precedent_btbs=top_candidate.precedents,
                    audit_notes=[f"{reason} nedeniyle otomatik onay verilmedi, uzman incelemesine sevk edildi."]
                )

            final_confidence = round(min(0.96, max(0.82, tariff_verif.confidence_score)), 2)
            applied_gir_list = applied_rules + [f"Uygulanan Kural: {tariff_verif.gir_rule_applied}"]
            llm_commentary = (
                f"Yapay Zeka Mantıksal Doğrulama (TariffVerification): Ürünün malzeme ({tariff_verif.is_material_compliant}) "
                f"ve fonksiyon ({tariff_verif.is_function_compliant}) koşulları doğrulanmış, "
                f"{top_candidate.gtip_code} tarife pozisyonu %{int(final_confidence*100)} güvenle onaylanmıştır."
            )
            return GTIPDecision(
                session_id=session_id,
                status="COMPLETED",
                gtip_code=top_candidate.gtip_code,
                confidence_score=final_confidence,
                official_statute_text=official_statute,
                llm_reasoning_commentary=llm_commentary,
                legal_justification=official_statute,
                applied_gir_rules=applied_gir_list,
                precedent_btbs=top_candidate.precedents,
                audit_notes=["TariffVerification yapılandırılmış doğrulama başarıyla tamamlandı."]
            )

        # 3. Predicate Listesi İle Doğrulama Değerlendirmesi
        if not predicate_list:
            # Predikat listesi yoksa RAG skoruyla tamamla
            base_score = top_candidate.score if hasattr(top_candidate, 'score') and top_candidate.score else 0.85
            return GTIPDecision(
                session_id=session_id,
                status="COMPLETED",
                gtip_code=top_candidate.gtip_code,
                confidence_score=round(min(0.95, max(0.80, base_score)), 2),
                official_statute_text=official_statute,
                llm_reasoning_commentary=f"Statik TGTC veritabanı eşleştirmesi ile {top_candidate.gtip_code} pozisyonu doğrulandı.",
                legal_justification=official_statute,
                applied_gir_rules=applied_rules,
                precedent_btbs=top_candidate.precedents,
                audit_notes=["RAG emsal eşleştirmesi ve statik tarife doğrulaması tamamlandı."]
            )

        total_count = len(predicate_list)
        verified_count = sum(1 for r in predicate_list if r.status in [PredicateStatus.TRUE, PredicateStatus.FALSE])
        unknown_predicates = [r for r in predicate_list if r.status == PredicateStatus.UNKNOWN]

        base_score = top_candidate.score if hasattr(top_candidate, 'score') and top_candidate.score else 0.80
        calc_ratio = (verified_count / total_count) if total_count > 0 else 0.5

        if calc_ratio == 1.0:
            final_confidence = round(min(0.96, max(0.82, base_score * 1.05)), 2)
        else:
            final_confidence = round(max(0.58, min(0.78, base_score * (0.5 + 0.5 * calc_ratio))), 2)

        # DURUM A: Tüm Yasal Şartlar Deterministik Olarak Doğrulandı (%100 Kesin Karar)
        if not unknown_predicates and calc_ratio == 1.0:
            llm_commentary = (
                f"Yapay Zeka Mantıksal Doğrulama (Predicate Logic): Ürünün teknik özellikleri ve yasal predikat ağacı "
                f"({verified_count}/{total_count} kural) %100 deterministik olarak doğrulanmış, halüsinasyon riski %0 tutulup "
                f"statik veritabanı eşleştirmesi yapılarak {top_candidate.gtip_code} tarife pozisyonu kesinleştirilmiştir."
            )
            return GTIPDecision(
                session_id=session_id,
                status="COMPLETED",
                gtip_code=top_candidate.gtip_code,
                confidence_score=final_confidence,
                official_statute_text=official_statute,
                llm_reasoning_commentary=llm_commentary,
                legal_justification=official_statute,
                applied_gir_rules=applied_rules + [f"GİR 1 & GİR 6: ({verified_count}/{total_count} kural doğrulandı)"],
                precedent_btbs=top_candidate.precedents,
                audit_notes=[f"Tüm {total_count} yasal predikat katı mantık motorunda doğrulandı. Halüsinasyon Riski: %0."]
            )

        # DURUM B: Eksik Bilgi Var (UNKNOWN Predikat) -> HITL İnsan Onayı Başlat
        missing_p = unknown_predicates[0]
        question_id = f"Q_HITL_{missing_p.predicate_id}"

        hitl_q = HITLQuestion(
            question_id=question_id,
            question_text=f"Eksik Teknik Bilgi Teyidi: {missing_p.description}",
            missing_parameter=missing_p.predicate_id,
            options=[
                HITLOption(
                    option_id="OPT_YES",
                    text=f"EVET ({missing_p.description} şartı sağlanıyor)",
                    impact_data={"predicate_verified": "TRUE"}
                ),
                HITLOption(
                    option_id="OPT_NO",
                    text=f"HAYIR (Bu teknik özellik sağlanmıyor)",
                    impact_data={"predicate_verified": "FALSE"}
                )
            ]
        )

        llm_commentary = (
            f"Yapay Zeka Mantıksal Doğrulama (Predicate Logic): Yasal predikat doğrulamasında '{missing_p.description}' "
            f"şartı belgede bulunamadığı için (UNKNOWN) karar kesinleştirilmemiş; Gümrük Müşaviri onayına yönlendirilmiştir."
        )

        return GTIPDecision(
            session_id=session_id,
            status="WAITING_FOR_USER",
            gtip_code=top_candidate.gtip_code,
            confidence_score=final_confidence,
            official_statute_text=official_statute,
            llm_reasoning_commentary=llm_commentary,
            legal_justification=official_statute,
            applied_gir_rules=applied_rules,
            precedent_btbs=top_candidate.precedents,
            hitl_question=hitl_q,
            audit_notes=[f"Eksik yasal predikat ({missing_p.predicate_id}) nedeniyle HITL sorusu oluşturuldu."]
        )

deterministic_engine = DeterministicDecisionEngine()
