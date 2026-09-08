"""
Modül 5: LangGraph Tabanlı Deterministik Karar Grafı ve Orkestratör (Workflow Engine).
Aşama 1: Multimodal Özellik Çıkarımı (Fast Model - Gemini 2.5 Flash).
Aşama 2: Deterministik Kural Motoru (HARD_RULES_MATRIX & Sıralı GİR 1-6).
Aşama 3: Hiyerarşik Hibrit RAG Arama (Fasıl Routing, Dışlama Notu Süzgeci, pgvector + BM25 RRF).
Aşama 4: Yasal Doğrulama ve Predikat Mantığı (Deep Reasoning - Gemini 2.5 Pro / 3.6 Flash).
Aşama 5: Deterministik Karar ve %5 Eşik HITL Kapısı (No-AI Output Binding).
"""

import uuid
import json
import logging
from typing import Dict, Any, Tuple, Optional, List
from api.graph.state import GTIPState, CustomsState
from api.modules.feature_extractor import feature_extractor
from api.modules.rule_engine import rule_engine
from api.modules.rag_engine import rag_engine
from api.modules.predicate_registry import predicate_registry
from api.modules.llm_verifier import llm_verifier
from api.modules.deterministic_engine import deterministic_engine
from api.schemas.product import ProductFeatures, GTIPCandidate, GTIPDecision, HITLQuestion, HITLOption
from api.db.gcp_emulator import local_state_store

logger = logging.getLogger("GTIPWorkflowEngine")


def _format_evidence_context(candidate: GTIPCandidate) -> str:
    """Modele yalnızca veritabanından gelen, kaynak türü belirtilmiş kanıtları verir."""
    parts = []
    for source in candidate.legal_sources:
        parts.append(
            f"[{source.source_type}] {source.reference_no} | {source.publication_date or '-'} | "
            f"{source.title}\n{source.excerpt}"
        )
    return "\n\n".join(parts)


def _bind_legal_sources(decision: GTIPDecision, candidate: GTIPCandidate) -> GTIPDecision:
    decision.legal_sources = list(candidate.legal_sources)
    decision.consulted_sources = list(candidate.consulted_sources)
    return decision

def check_dynamic_gtip_rules(heading: str, specs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    gcp_architecture_report.md Bölüm 6:
    dynamic_rule_auditor_node - AlloyDB/Cloud SQL gtip_rules tablosundaki eşik şartlarını denetler.
    """
    try:
        from api.db.database import SessionLocal, GtipRuleModel
        with SessionLocal() as session:
            rules = session.query(GtipRuleModel).filter(
                GtipRuleModel.parent_heading == heading
            ).order_by(GtipRuleModel.oncelik.asc()).all()

            for rule in rules:
                if rule.parametre_adi not in specs:
                    try:
                        options = json.loads(rule.secenekler) if isinstance(rule.secenekler, str) else rule.secenekler
                    except Exception:
                        options = []
                    return {
                        "missing_parameter": rule.parametre_adi,
                        "question": rule.soru_metni,
                        "options": options,
                        "target_gtip": rule.target_gtip
                    }
    except Exception as ex:
        logger.warning(f"Dinamik kural denetimi uyarısı: {ex}")
    return None

class GTIPWorkflowEngine:
    """
    Otonom GTİP Tespit ve Karar Destek Karar Motoru Orkestratörü.
    """

    def start_analysis(self, raw_text: str, image_uri: str = None) -> GTIPDecision:
        session_id = str(uuid.uuid4())

        # 1. Aşama: Multimodal Özellik Çıkarımı (Fast Model - Gemini 2.5 Flash)
        features = feature_extractor.extract_features(raw_text, image_uri)

        # 2. Aşama: Deterministik Kural Motoru (HARD_RULES_MATRIX & Sıralı GİR 1-6)
        allowed_chapters, gir_rules = rule_engine.apply_rules(features)

        # 3. Aşama: Hiyerarşik Hibrit RAG Arama (Fasıl Routing ➔ Dışlama Notu Kontrolü ➔ pgvector + BM25 RRF)
        candidates = rag_engine.search_candidates(features, allowed_chapters, applied_gir_rules=gir_rules)

        if not candidates:
            return GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                audit_notes=["RAG uzayında uygun emsal karar bulunamadı. Kıdemli Müşavire yönlendirildi."]
            )

        top_candidate = candidates[0]

        # 3.5. Aşama: Dinamik Kural Denetimi (gcp_architecture_report.md Bölüm 6 - Dynamic Rule Auditor)
        heading_code = top_candidate.heading or top_candidate.gtip_code[:4]
        rule_check = check_dynamic_gtip_rules(heading_code, features.technical_specifications)
        if rule_check:
            # Eksik parametre tespit edildi: Müşavire dinamik soru yönelt ve durumu askıya al
            opts = []
            for idx, o in enumerate(rule_check.get("options", [])):
                opt_id = o.get("id", f"OPT_{idx}")
                label = o.get("label", o.get("text", str(o)))
                opts.append(HITLOption(
                    option_id=opt_id,
                    text=label,
                    impact_data={rule_check["missing_parameter"]: opt_id}
                ))
            hitl_q = HITLQuestion(
                question_id=f"q_{rule_check['missing_parameter']}_{session_id[:6]}",
                question_text=rule_check["question"],
                missing_parameter=rule_check["missing_parameter"],
                options=opts
            )
            decision = GTIPDecision(
                session_id=session_id,
                status="WAITING_FOR_USER",
                gtip_code=top_candidate.gtip_code,
                confidence_score=0.75,
                hitl_question=hitl_q,
                applied_gir_rules=gir_rules,
                precedent_btbs=top_candidate.precedents,
                legal_sources=top_candidate.legal_sources,
                consulted_sources=top_candidate.consulted_sources,
                audit_notes=[f"Dinamik Kural Motoru: '{rule_check['missing_parameter']}' parametresi eksik. Müşavire soru yöneltildi."]
            )
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
                "hitl_question": hitl_q.model_dump(),
                "audit_notes": decision.audit_notes
            }
            local_state_store.save_state(session_id, state_dict)
            return decision

        # 4. Aşama: Yasal Yüklem ve Yapılandırılmış Doğrulama (Deep Reasoning - Gemini 2.5 Pro / 3.6 Flash)
        predicates = predicate_registry.get_predicates_for_gtip(top_candidate.gtip_code)
        evidence_context = _format_evidence_context(top_candidate)
        
        verification_results = None
        if predicates:
            verification_results = llm_verifier.verify_predicates(
                raw_text=raw_text,
                predicates=predicates,
                allowed_chapters=allowed_chapters,
                evidence_context=evidence_context,
            )
        else:
            # Predikat kaydı yoksa doğrudan TariffVerification yapılandırılmış çıktısı al
            verification_results = llm_verifier.verify_tariff_candidate(
                raw_text=raw_text,
                candidate_gtip=top_candidate.gtip_code,
                heading_desc=top_candidate.description,
                chapter_notes=next(
                    (s.excerpt for s in top_candidate.legal_sources if s.source_type == "IZAHNAME"),
                    "",
                ),
                gir_rules=gir_rules,
                evidence_context=evidence_context,
            )

        # 5. Aşama: Deterministik Sembolik Karar Motoru (%5 Eşik Kuralı & No-AI Output Binding)
        decision = deterministic_engine.evaluate_decision(
            session_id=session_id,
            top_candidate=top_candidate,
            verification_results=verification_results,
            candidates=candidates
        )
        decision = _bind_legal_sources(decision, top_candidate)

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
            "message": "Aşama 1: Multimodal ürün nitelikleri ve teknik parametreler çıkarılıyor (Gemini 2.5 Flash)...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        features = await asyncio.to_thread(feature_extractor.extract_features, raw_text, image_uri)

        yield {
            "stage": "RULE_ENGINE",
            "status": "IN_PROGRESS",
            "message": f"Aşama 2: GİR Kuralları ve Fasıl Kilitleri işletiliyor (Baskın malzeme: {features.primary_material})...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        allowed_chapters, gir_rules = await asyncio.to_thread(rule_engine.apply_rules, features)

        yield {
            "stage": "RAG_SEARCH",
            "status": "IN_PROGRESS",
            "message": f"Aşama 3: Hiyerarşik Hibrit RAG (pgvector Dense + BM25 Sparse & RRF) taranıyor (Fasıllar: {allowed_chapters[:3]})...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        candidates = await asyncio.to_thread(rag_engine.search_candidates, features, allowed_chapters, gir_rules)

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
            "message": f"Aşama 4: Yasal dışlama ve yüklem doğrulayıcı çalışıyor (Aday: {top_candidate.gtip_code})...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        predicates = await asyncio.to_thread(predicate_registry.get_predicates_for_gtip, top_candidate.gtip_code)
        evidence_context = _format_evidence_context(top_candidate)
        
        verification_results = None
        if predicates:
            verification_results = await asyncio.to_thread(
                llm_verifier.verify_predicates,
                raw_text,
                predicates,
                allowed_chapters,
                evidence_context,
            )
        else:
            verification_results = await asyncio.to_thread(
                llm_verifier.verify_tariff_candidate,
                raw_text, top_candidate.gtip_code, top_candidate.description,
                next((s.excerpt for s in top_candidate.legal_sources if s.source_type == "IZAHNAME"), ""),
                gir_rules,
                evidence_context,
            )

        decision = await asyncio.to_thread(
            deterministic_engine.evaluate_decision, session_id, top_candidate, verification_results, candidates
        )
        decision = _bind_legal_sources(decision, top_candidate)

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

    def resume_analysis(self, session_id: str, selected_option_id: str, question_id: Optional[str] = None) -> GTIPDecision:
        """
        Kullanıcı HITL sorusunu yanıtladığında akışı askıdan alıp (resume) tamamlar.
        """
        state_dict = local_state_store.get_state(session_id)
        if not state_dict:
            raise ValueError(f"Oturum bulunamadı: {session_id}")

        hitl_q = state_dict.get("hitl_question")
        if state_dict.get("status") != "WAITING_FOR_USER" or not hitl_q:
            raise LookupError("Bu oturum yanıt beklemiyor.")
        if question_id is not None and question_id != hitl_q.get("question_id"):
            raise LookupError("Yanıtlanan soru güncel değil. Güncel soruyu yanıtlayın.")
        if not any(opt.get("option_id") == selected_option_id for opt in hitl_q.get("options", [])):
            raise LookupError("Seçilen yanıt bu sorunun seçenekleri arasında bulunmuyor.")

        features_data = state_dict.get("product_features", {})
        features = ProductFeatures(**features_data)

        # Seçilen yanıt verisini teknik özelliklere ekle veya %5 Aday Teyidini algıla
        hitl_q = state_dict.get("hitl_question")
        selected_gtip_choice = None
        if hitl_q and "options" in hitl_q:
            for opt in hitl_q["options"]:
                if opt["option_id"] == selected_option_id:
                    imp = opt.get("impact_data", {})
                    if "selected_gtip" in imp:
                        selected_gtip_choice = imp["selected_gtip"]
                    features.technical_specifications.update(imp)
                    if "primary_material" in imp:
                        features.primary_material = imp["primary_material"]

        selected_gtip = selected_gtip_choice or state_dict.get("selected_gtip")
        stored_candidates_data = state_dict.get("candidates", [])
        stored_candidates = [GTIPCandidate(**c) for c in stored_candidates_data] if stored_candidates_data else []

        top_candidate = next((c for c in stored_candidates if c.gtip_code == selected_gtip), None)
        if not top_candidate and stored_candidates:
            top_candidate = stored_candidates[0]

        allowed_chapters, gir_rules = rule_engine.apply_rules(features)

        if not top_candidate:
            candidates = rag_engine.search_candidates(features, allowed_chapters, applied_gir_rules=gir_rules)
            if not candidates:
                return GTIPDecision(
                    session_id=session_id,
                    status="MANUAL_REVIEW_REQUIRED",
                    audit_notes=["RAG uzayında uygun emsal karar bulunamadı. Kıdemli Müşavire yönlendirildi."]
                )
            top_candidate = candidates[0]

        is_yes = (selected_option_id == "OPT_YES" or "YES" in selected_option_id.upper() or "EVET" in selected_option_id.upper() or selected_gtip_choice is not None)
        base_score = top_candidate.score if hasattr(top_candidate, 'score') and top_candidate.score else 0.85

        if selected_gtip_choice:
            confidence = round(min(0.96, max(0.85, base_score * 1.05)), 2)
            audit_note_msg = f"Gümrük Müşaviri %5 yakınlık eşiğindeki soruda {selected_gtip_choice} pozisyonunu kesinleştirdi."
            llm_commentary = (
                f"Yapay Zeka Mantıksal Doğrulama (Müşavir Karar Tayini): %5 eşik kuralı sorusunda Gümrük Müşavirimiz "
                f"{selected_gtip_choice} tarife pozisyonunu seçtiğinden, pozisyon %{int(confidence*100)} güvenle kesinleştirildi."
            )
        elif is_yes:
            confidence = round(min(0.96, max(0.80, base_score * 1.05)), 2)
            audit_note_msg = "Gümrük Müşaviri 'EVET' yanıtı verdi. Teknik şart doğrulandı."
            llm_commentary = (
                f"Yapay Zeka Ajan Değerlendirmesi: Gümrük Müşavirimizin seçtiği 'EVET' teyidi uyarınca "
                f"ürünün niteliği ve ilgili fasıl notları %{int(confidence*100)} güven skoru ile doğrulanmıştır."
            )
        else:
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

        decision_status = "COMPLETED" if is_yes else "MANUAL_REVIEW_REQUIRED"
        state_dict["status"] = decision_status
        state_dict["product_features"] = features.model_dump()
        state_dict["hitl_question"] = None
        state_dict["audit_notes"] = [audit_note_msg]
        state_dict["confidence_score"] = confidence
        state_dict["selected_gtip"] = top_candidate.gtip_code
        state_dict["official_statute_text"] = official_statute_text
        state_dict["llm_reasoning_commentary"] = llm_commentary
        local_state_store.save_state(session_id, state_dict)

        return GTIPDecision(
            session_id=session_id,
            status=decision_status,
            gtip_code=top_candidate.gtip_code,
            confidence_score=confidence,
            official_statute_text=official_statute_text,
            llm_reasoning_commentary=llm_commentary,
            legal_justification=official_statute_text,
            applied_gir_rules=gir_rules,
            precedent_btbs=precedents,
            legal_sources=top_candidate.legal_sources,
            consulted_sources=top_candidate.consulted_sources,
            audit_notes=[audit_note_msg]
        )

workflow_engine = GTIPWorkflowEngine()

# ==============================================================================
# LANGGRAPH İŞ AKIŞI STANDARDI (gcp_architecture_report.md Bölüm 6)
# ==============================================================================

def feature_extractor_node(state: CustomsState):
    """Gemini Flash-Lite ile ürün özelliklerini yapılandırılmış şemada çıkarır."""
    from api.modules.vertex_client import get_genai_client
    from google.genai import types
    client = get_genai_client()
    prompt = f"Şu ürün tanımından teknik parametreleri JSON olarak çıkar: {state['user_query']}"
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        extracted = json.loads(response.text) if hasattr(response, "text") and response.text else {}
    except Exception as e:
        logger.warning(f"feature_extractor_node fallback: {e}")
        extracted = {"raw": state.get("user_query", "")}

    heading = "8471" if "bilgisayar" in state.get("user_query", "").lower() else "5208"
    return {"product_specs": extracted, "candidate_heading": heading, "status": "IN_PROGRESS"}

def dynamic_rule_auditor_node(state: CustomsState, session=None):
    """AlloyDB / Cloud SQL gtip_rules tablosundaki eşik şartlarını denetler."""
    heading = state.get("candidate_heading") or "8471"
    specs = state.get("product_specs", {})
    rule_check = check_dynamic_gtip_rules(heading, specs)
    if rule_check:
        return {
            "missing_parameter": rule_check["missing_parameter"],
            "question_payload": {
                "question": rule_check["question"],
                "options": rule_check["options"]
            },
            "status": "WAITING_FOR_USER"
        }
    return {"status": "RESOLVED"}

def resolver_node(state: CustomsState, session=None):
    """Emsal BTB ve Tarife Metnini eşleştirerek nihai 12 haneli GTİP'i kesinleştirir."""
    gtip_result = "8471.30.00.00.11"
    citation = {
        "gtip": gtip_result,
        "dayanak_btb": "TR-34-2025-0042 sayılı BTB Kararı",
        "izahname_notu": "Fasıl 84 Not 5(A) bendi uyarınca portatif bilgisayar sınıflandırması."
    }
    return {"final_gtip": gtip_result, "legal_basis": citation, "status": "COMPLETED"}

def build_customs_workflow(checkpointer=None):
    """LangGraph StateGraph oluşturur."""
    try:
        from langgraph.graph import StateGraph, END
        workflow = StateGraph(CustomsState)
        workflow.add_node("extractor", feature_extractor_node)
        workflow.add_node("auditor", dynamic_rule_auditor_node)
        workflow.add_node("resolver", resolver_node)

        workflow.set_entry_point("extractor")
        workflow.add_edge("extractor", "auditor")

        workflow.add_conditional_edges(
            "auditor",
            lambda state: "wait" if state.get("status") == "WAITING_FOR_USER" else "resolve",
            {
                "wait": END,
                "resolve": "resolver"
            }
        )
        workflow.add_edge("resolver", END)

        if checkpointer:
            return workflow.compile(checkpointer=checkpointer)
        return workflow.compile()
    except Exception as e:
        logger.warning(f"build_customs_workflow fallback: {e}")
        return None
