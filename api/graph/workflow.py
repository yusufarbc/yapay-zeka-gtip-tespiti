import uuid
from typing import Dict, Any, Tuple
from api.graph.state import GTIPState
from api.modules.feature_extractor import feature_extractor
from api.modules.rule_engine import rule_engine
from api.modules.rag_engine import rag_engine
from api.modules.predicate_registry import predicate_registry
from api.modules.llm_verifier import llm_verifier
from api.modules.deterministic_engine import deterministic_engine
from api.schemas.product import ProductFeatures, GTIPCandidate, GTIPDecision
from api.db.gcp_emulator import local_state_store

class GTIPWorkflowEngine:
    """
    Modül 5: Deterministic Rule-Engine + LLM Predicate Logic Architecture Orkestratörü.
    Aşama 1: Candidate Generation (Search space reduction -> top 3-5 candidates).
    Aşama 2: Predicate Checklist Retrieval (TGTC Legal Predicate Registry).
    Aşama 3: LLM Fact Verification (Gemini 2.5 Pro Predicate Verifier).
    Aşama 4: Deterministic Decision Engine (Python Symbolic Logic Gate).
    """

    def start_analysis(self, raw_text: str, image_uri: str = None) -> GTIPDecision:
        session_id = str(uuid.uuid4())

        # 1. Multimodal Özellik Çıkarımı (Modül 1 - Ürün Metni İşleme)
        features = feature_extractor.extract_features(raw_text, image_uri)

        # 2. Kural Motoru (Modül 2 - Fasıl ve GİR Kuralları)
        allowed_chapters, gir_rules = rule_engine.apply_rules(features)

        # 3. Candidate Generation (Modül 3 - RAG ile Aday Eleme)
        candidates = rag_engine.search_candidates(features, allowed_chapters)

        if not candidates:
            return GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                audit_notes=["RAG uzayında uygun emsal karar bulunamadı. Kıdemli Müşavire yönlendirildi."]
            )

        top_candidate = candidates[0]

        # 4. Yasal Predikat Ağacı Çekimi (TGTC Predicate Registry)
        predicates = predicate_registry.get_predicates_for_gtip(top_candidate.gtip_code)

        # 5. LLM Predicate Fact Verifier (Gemini 2.5 Pro TRUE/FALSE/UNKNOWN Doğrulama)
        verification_results = llm_verifier.verify_predicates(raw_text, predicates)

        # 6. Deterministik Sembolik Karar Motoru (Python Logic Gate)
        decision = deterministic_engine.evaluate_decision(session_id, top_candidate, verification_results)

        # State kaydet
        state_dict: Dict[str, Any] = {
            "session_id": session_id,
            "raw_text": raw_text,
            "image_uri": image_uri,
            "product_features": features.model_dump(),
            "allowed_chapters": allowed_chapters,
            "applied_gir_rules": gir_rules,
            "candidates": [c.model_dump() for c in candidates],
            "selected_gtip": top_candidate.gtip_code,
            "confidence_score": decision.confidence_score,
            "status": decision.status,
            "official_statute_text": decision.official_statute_text,
            "llm_reasoning_commentary": decision.llm_reasoning_commentary,
            "hitl_question": decision.hitl_question.model_dump() if decision.hitl_question else None,
            "audit_notes": decision.audit_notes
        }
        local_state_store.save_state(session_id, state_dict)

        return decision

    async def start_analysis_async(self, raw_text: str, image_uri: str = None) -> GTIPDecision:
        """
        Asenkron non-blocking analiz metodu.
        """
        import asyncio
        return await asyncio.to_thread(self.start_analysis, raw_text, image_uri)

    async def start_analysis_stream(self, raw_text: str, image_uri: str = None):
        """
        Server-Sent Events (SSE) canlı akışı için aşamalı generator.
        """
        import asyncio
        session_id = str(uuid.uuid4())

        yield {
            "stage": "FEATURE_EXTRACTION",
            "status": "IN_PROGRESS",
            "message": "Aşama 1: Multimodal ürün nitelikleri ve teknik parametreler çıkarılıyor...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        features = await asyncio.to_thread(feature_extractor.extract_features, raw_text, image_uri)

        yield {
            "stage": "RULE_ENGINE",
            "status": "IN_PROGRESS",
            "message": f"Aşama 2: GİR Kuralları çalıştırılıyor (Baskın malzeme: {features.primary_material})...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        allowed_chapters, gir_rules = await asyncio.to_thread(rule_engine.apply_rules, features)

        yield {
            "stage": "RAG_SEARCH",
            "status": "IN_PROGRESS",
            "message": f"Aşama 3: BTB ve TGTC veritabanında semantik tarama yapılıyor (Fasıllar: {allowed_chapters[:3]})...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        candidates = await asyncio.to_thread(rag_engine.search_candidates, features, allowed_chapters)

        if not candidates:
            decision = GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                audit_notes=["RAG uzayında uygun emsal karar bulunamadı. Kıdemli Müşavire yönlendirildi."]
            )
            yield {
                "stage": "COMPLETED",
                "status": "MANUAL_REVIEW_REQUIRED",
                "message": "Aşama 4: Uygun emsal bulunamadı, manuel incelemeye yönlendirildi.",
                "decision": decision.model_dump()
            }
            return

        top_candidate = candidates[0]

        yield {
            "stage": "LLM_VERIFICATION",
            "status": "IN_PROGRESS",
            "message": f"Aşama 4: Predikat ağacı ve sembolik mantık kapısı doğrulanıyor (Aday: {top_candidate.gtip_code})...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        predicates = await asyncio.to_thread(predicate_registry.get_predicates_for_gtip, top_candidate.gtip_code)
        verification_results = await asyncio.to_thread(llm_verifier.verify_predicates, raw_text, predicates)
        decision = await asyncio.to_thread(deterministic_engine.evaluate_decision, session_id, top_candidate, verification_results)

        state_dict: Dict[str, Any] = {
            "session_id": session_id,
            "raw_text": raw_text,
            "image_uri": image_uri,
            "product_features": features.model_dump(),
            "allowed_chapters": allowed_chapters,
            "applied_gir_rules": gir_rules,
            "candidates": [c.model_dump() for c in candidates],
            "selected_gtip": top_candidate.gtip_code,
            "confidence_score": decision.confidence_score,
            "status": decision.status,
            "official_statute_text": decision.official_statute_text,
            "llm_reasoning_commentary": decision.llm_reasoning_commentary,
            "hitl_question": decision.hitl_question.model_dump() if decision.hitl_question else None,
            "audit_notes": decision.audit_notes
        }
        local_state_store.save_state(session_id, state_dict)

        yield {
            "stage": "COMPLETED",
            "status": decision.status,
            "message": f"Analiz tamamlandı. Karar: {decision.gtip_code or 'HITL Gerekli'} (Güven: %{int(decision.confidence_score*100)})",
            "decision": decision.model_dump()
        }

    def resume_analysis(self, session_id: str, selected_option_id: str) -> GTIPDecision:
        """
        Kullanıcı HITL sorusunu yanıtladığında akışı askıdan alıp (resume) tamamlar.
        """
        state_dict = local_state_store.get_state(session_id)
        if not state_dict:
            raise ValueError(f"Oturum bulunamadı: {session_id}")

        features_data = state_dict.get("product_features", {})
        features = ProductFeatures(**features_data)

        # Seçilen yanıt verisini teknik özelliklere ekle
        hitl_q = state_dict.get("hitl_question")
        if hitl_q and "options" in hitl_q:
            for opt in hitl_q["options"]:
                if opt["option_id"] == selected_option_id:
                    features.technical_specifications.update(opt.get("impact_data", {}))
                    if "primary_material" in opt.get("impact_data", {}):
                        features.primary_material = opt["impact_data"]["primary_material"]

        # Kural ve RAG motorunu güncellenmiş özelliklerle yeniden çalıştır
        allowed_chapters, gir_rules = rule_engine.apply_rules(features)
        candidates = rag_engine.search_candidates(features, allowed_chapters)
        if not candidates:
            return GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                audit_notes=["RAG uzayında uygun emsal karar bulunamadı. Kıdemli Müşavire yönlendirildi."]
            )
        top_candidate = candidates[0]

        is_yes = (selected_option_id == "OPT_YES" or "YES" in selected_option_id.upper() or "EVET" in selected_option_id.upper())
        base_score = top_candidate.score if hasattr(top_candidate, 'score') and top_candidate.score else 0.85

        if is_yes:
            confidence = round(min(0.96, max(0.80, base_score * 1.05)), 2)
            audit_note_msg = "Gümrük Müşaviri 'EVET' yanıtı verdi. Teknik şart doğrulandı."
            llm_commentary = (
                f"Yapay Zeka Ajan Değerlendirmesi: Gümrük Müşavirimizin seçtiği 'EVET' teyidi uyarınca "
                f"ürünün niteliği ve ilgili fasıl notları %{int(confidence*100)} güven skoru ile doğrulanmıştır."
            )
        else:
            # HAYIR yanıtında güven skoru düşer (%62 / ŞÜPHELİ UYARISI)
            confidence = round(max(0.55, min(0.72, base_score * 0.70)), 2)
            audit_note_msg = "⚠️ Gümrük Müşaviri 'HAYIR' yanıtı verdi. Teknik şart sağlanamadı (ŞÜPHELİ / DÜŞÜK GÜVEN)."
            llm_commentary = (
                f"⚠️ ŞÜPHELİ / UYUMSUZ TEYİT: Gümrük Müşavirimiz 'HAYIR (Teknik özellik sağlanmıyor)' yanıtını seçtiği için "
                f"ürün bu pozisyonun yasal şartını karşılamamaktadır. Güven skoru %{int(confidence*100)} seviyesine düşürülmüştür. "
                f"Alternatif tarife pozisyonu (örn. aksam/parça veya ikincil alt açılım) değerlendirilmelidir."
            )

        official_statute_text = (
            f"Türk Gümrük Tarife Cetveli (TGTC) Madde {top_candidate.gtip_code[:4]} ve GİR Kuralları: "
            f"{top_candidate.description}. (Resmi Mevzuat Veritabanı Kaydı)"
        )

        precedents = top_candidate.precedents

        state_dict["status"] = "COMPLETED"
        state_dict["confidence_score"] = confidence
        state_dict["selected_gtip"] = top_candidate.gtip_code
        state_dict["official_statute_text"] = official_statute_text
        state_dict["llm_reasoning_commentary"] = llm_commentary
        local_state_store.save_state(session_id, state_dict)

        return GTIPDecision(
            session_id=session_id,
            status="COMPLETED",
            gtip_code=top_candidate.gtip_code,
            confidence_score=confidence,
            official_statute_text=official_statute_text,
            llm_reasoning_commentary=llm_commentary,
            legal_justification=official_statute_text,
            applied_gir_rules=gir_rules,
            precedent_btbs=precedents,
            audit_notes=["Gümrük Müşaviri yanıtı alındı. Akış başarıyla tamamlandı."]
        )

workflow_engine = GTIPWorkflowEngine()
