"""
Modül 5: LangGraph Tabanlı Deterministik Karar Grafı ve Orkestratör (Workflow Engine).
Aşama 1: Multimodal Özellik Çıkarımı (Fast Model - Gemini 2.5 Flash).
Aşama 2: Deterministik Kural Motoru (HARD_RULES_MATRIX & Sıralı GİR 1-6).
Aşama 3: Hiyerarşik Hibrit RAG Arama (Fasıl Routing, Dışlama Notu Süzgeci, pgvector + BM25 RRF).
Aşama 4: Yasal Doğrulama ve Predikat Mantığı (Deep Reasoning - Gemini 2.5 Pro / 3.6 Flash).
Aşama 5: Deterministik Karar ve %5 Eşik HITL Kapısı (No-AI Output Binding).
"""
from __future__ import annotations

import uuid
import json
import logging
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Tuple, Optional, List
from api.graph.state import GTIPState, CustomsState
from api.modules.feature_extractor import feature_extractor
from api.modules.rule_engine import rule_engine
from api.modules.rag_engine import rag_engine
from api.modules.predicate_registry import predicate_registry
from api.modules.llm_verifier import llm_verifier
from api.modules.deterministic_engine import deterministic_engine
from api.modules.negation_engine import negation_engine
from api.schemas.product import ProductFeatures, GTIPCandidate, GTIPDecision, HITLQuestion, HITLOption, PrecedentBTB
from api.schemas.predicate import CandidateSelectionStatus, PredicateStatus
from api.db.gcp_emulator import local_state_store
from api.db.database import SessionLocal, validate_leaf_gtip
from api.modules.discriminator_engine import DiscriminatorQuestion
from api.modules.legal_authority import validate_candidate_evidence

logger = logging.getLogger("GTIPWorkflowEngine")


def get_customs_trade_measures(gtip_code: Optional[str]) -> Dict[str, Any]:
    """GTİP koduna ait Ticaret Politikası Önlemlerini (İGV, TAREKS, KDV, Gözetim) döndürür."""
    clean = re.sub(r"\D", "", str(gtip_code or ""))
    chap = clean[:2] if len(clean) >= 2 else ""
    igv = 20.0 if chap in {"85", "84", "64", "39", "94", "73"} else 0.0
    tareks = "Tüketici Güvenliği ve Denetimi Tebliği" if chap in {"85", "84", "95", "90"} else None
    kdv = 20.0
    surveillance = "İthalatta Gözetim Uygulanmasına İlişkin Tebliğ" if chap in {"85", "64", "73"} else None
    return {
        "kdv_rate": kdv,
        "additional_duty_rate": igv,
        "tareks_required": tareks is not None,
        "tareks_detail": tareks,
        "surveillance_measure": surveillance,
    }


def _mark_pipeline_stage(session_id: str, stage: str, started_at: float) -> float:
    """Her pahalı aşamayı Cloud Logging'de ayrı ölçülebilir hale getirir."""
    now = time.perf_counter()
    logger.info(
        "[PipelineTiming] session=%s stage=%s duration_ms=%.2f",
        session_id,
        stage,
        (now - started_at) * 1000,
    )
    return now


def _as_hitl_question(question: DiscriminatorQuestion) -> HITLQuestion:
    return HITLQuestion(
        question_id=f"disc_{question.parameter_name}_{question.session_id[:8]}",
        question_text=question.question_text,
        missing_parameter=question.parameter_name,
        options=[
            HITLOption(
                option_id=f"DISC_{index}",
                text=label,
                impact_data={"selected_branch": question.target_branches[str(index)]},
            )
            for index, label in enumerate(question.options)
        ],
    )


def _format_evidence_context(candidate: GTIPCandidate) -> str:
    """Modele yalnızca veritabanından gelen, kaynak türü belirtilmiş kanıtları verir."""
    parts = []
    for source in candidate.legal_sources:
        parts.append(
            f"[{source.source_type} | {source.legal_role}] {source.reference_no} | {source.publication_date or '-'} | "
            f"{source.title}\n{source.excerpt}"
        )
    return "\n\n".join(parts)


def _bind_legal_sources(decision: GTIPDecision, candidate: GTIPCandidate) -> GTIPDecision:
    decision.legal_sources = list(candidate.legal_sources)
    decision.consulted_sources = list(candidate.consulted_sources)
    return decision


def _exact_locked_candidate_index(tree_result, candidates: List[GTIPCandidate]) -> Optional[int]:
    """Hiyerarşik ağacın kilitlediği tek yaprağı kapalı-küme modeline tekrar seçtirmez."""
    locked_gtip = str((tree_result.traversal_state or {}).get("locked_gtip") or "")
    locked_digits = re.sub(r"\D", "", locked_gtip)
    if len(locked_digits) != 12:
        return None
    matches = [
        index for index, candidate in enumerate(candidates)
        if re.sub(r"\D", "", candidate.gtip_code) == locked_digits
    ]
    return matches[0] if len(matches) == 1 else None

def _comparable_value(value: Any) -> Any:
    raw = str(value or "").strip().lower().replace(",", ".")
    if raw in {"true", "evet", "yes", "var", "1"}:
        return True
    if raw in {"false", "hayır", "hayir", "no", "yok", "0"}:
        return False
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if match:
        try:
            return Decimal(match.group(0))
        except InvalidOperation:
            pass
    return raw


def _condition_matches(actual: Any, operator: str, expected: Any) -> bool:
    left = _comparable_value(actual)
    right = _comparable_value(expected)
    op = str(operator or "==").strip().lower()
    try:
        if op in {"==", "="}:
            return left == right
        if op in {"!=", "<>"}:
            return left != right
        if op == "<=":
            return left <= right
        if op == "<":
            return left < right
        if op == ">=":
            return left >= right
        if op == ">":
            return left > right
        if op == "contains":
            return str(right).lower() in str(left).lower()
        if op == "in":
            values = expected if isinstance(expected, (list, tuple, set)) else str(expected).split("|")
            return str(actual).strip().lower() in {str(value).strip().lower() for value in values}
    except (TypeError, InvalidOperation):
        return False
    return False


def _option_impact_value(option: Dict[str, Any]) -> str:
    if option.get("value") is not None:
        return str(option["value"])
    option_id = str(option.get("id") or "").lower()
    known_values = {
        "opt_le_10kg": "10kg",
        "opt_gt_10kg": "10.01kg",
        "opt_has_both": "true",
        "opt_no_both": "false",
        "opt_cotton_gte_85": "85%",
        "opt_cotton_lt_85": "84.99%",
    }
    return known_values.get(option_id, str(option.get("id") or option.get("label") or ""))


def check_dynamic_gtip_rules(
    heading: str,
    specs: Dict[str, Any],
    candidate_gtip: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
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
                if candidate_gtip and rule.target_gtip:
                    if re.sub(r"\D", "", str(candidate_gtip)) != re.sub(r"\D", "", str(rule.target_gtip)):
                        continue
                if rule.parametre_adi not in specs:
                    try:
                        options = json.loads(rule.secenekler) if isinstance(rule.secenekler, str) else rule.secenekler
                    except Exception:
                        options = []
                    return {
                        "status": "MISSING",
                        "missing_parameter": rule.parametre_adi,
                        "question": rule.soru_metni,
                        "options": options,
                        "target_gtip": rule.target_gtip
                    }
                if not _condition_matches(specs.get(rule.parametre_adi), rule.kosul_operatoru, rule.esik_deger):
                    return {
                        "status": "FAILED",
                        "missing_parameter": rule.parametre_adi,
                        "target_gtip": rule.target_gtip,
                        "actual_value": specs.get(rule.parametre_adi),
                        "operator": rule.kosul_operatoru,
                        "expected_value": rule.esik_deger,
                    }
    except Exception as ex:
        logger.warning(f"Dinamik kural denetimi uyarısı: {ex}")
    return None

class GTIPWorkflowEngine:
    """
    Otonom GTİP Tespit ve Karar Destek Karar Motoru Orkestratörü.
    """

    def _pause_for_discriminator(
        self,
        session_id: str,
        raw_text: str,
        image_uri: Optional[str],
        features: ProductFeatures,
        allowed_chapters: List[str],
        gir_rules: List[str],
        tree_result,
    ) -> GTIPDecision:
        hitl_question = _as_hitl_question(tree_result.discriminator_question)
        traversal = dict(tree_result.traversal_state)
        provisional_code = next((
            str(branch.get("gtip_code")) for branch in traversal.get("branches", [])
            if branch.get("gtip_code")
        ), None)
        provisional_description = next((
            str(branch.get("description") or "") for branch in traversal.get("branches", [])
            if branch.get("gtip_code") == provisional_code
        ), "")
        decision = GTIPDecision(
            session_id=session_id,
            status="WAITING_FOR_USER",
            gtip_code=provisional_code,
            confidence_score=0.0,
            official_statute_text=f"2026 TGTC {provisional_code}: {provisional_description}",
            hitl_question=hitl_question,
            applied_gir_rules=gir_rules,
            audit_notes=[
                f"{traversal.get('pending_level', 'TARİFE')} seviyesinde iki yakın dal "
                "tespit edildi; yaprak araması yapılmadan ayırt edici soru soruldu."
            ],
        )
        local_state_store.save_state(session_id, {
            "session_id": session_id,
            "raw_text": raw_text,
            "image_uri": image_uri,
            "product_features": features.model_dump(),
            "allowed_chapters": allowed_chapters,
            "applied_gir_rules": gir_rules,
            "candidates": [],
            "selected_gtip": None,
            "confidence_score": 0.0,
            "status": decision.status,
            "hitl_question": hitl_question.model_dump(),
            "discriminator_traversal": traversal,
            "audit_notes": decision.audit_notes,
        })
        return decision

    def _pause_for_candidate_disambiguation(
        self,
        session_id: str,
        raw_text: str,
        image_uri: Optional[str],
        features: ProductFeatures,
        allowed_chapters: List[str],
        gir_rules: List[str],
        candidates: List[GTIPCandidate],
        selection: Any,
    ) -> GTIPDecision:
        question_text = ""
        if getattr(selection, "missing_information", None):
            question_text = str(selection.missing_information[0]).strip()
        if not question_text:
            question_text = "Ürününüz aşağıdaki GTİP ayrımlarından hangisine uygundur?"

        options: List[HITLOption] = []
        for idx, cand in enumerate(candidates[:4]):
            cand_id = f"C{idx + 1}"
            options.append(
                HITLOption(
                    option_id=cand_id,
                    text=f"{cand.gtip_code} — {cand.description[:400]}",
                    impact_data={
                        "selected_gtip": cand.gtip_code,
                        "selected_branch": cand.gtip_code,
                    },
                )
            )
        options.append(
            HITLOption(
                option_id="UNKNOWN",
                text="Bilinmiyor / Emin değilim (Gümrük Müşaviri İncelemesi)",
                impact_data={"selected_branch": ""},
            )
        )

        hitl_question = HITLQuestion(
            question_id=f"disambig_{session_id[:8]}",
            question_text=question_text,
            missing_parameter="tarife_ayrimi",
            options=options,
        )

        provisional_code = candidates[0].gtip_code if candidates else None
        provisional_description = candidates[0].description if candidates else ""

        decision = GTIPDecision(
            session_id=session_id,
            status="WAITING_FOR_USER",
            gtip_code=provisional_code,
            confidence_score=0.0,
            official_statute_text=f"2026 TGTC {provisional_code}: {provisional_description}",
            hitl_question=hitl_question,
            applied_gir_rules=gir_rules,
            audit_notes=(getattr(selection, "reasoning_points", []) or [])[:4],
        )

        state_dict: Dict[str, Any] = {
            "session_id": session_id,
            "raw_text": raw_text,
            "image_uri": image_uri,
            "product_features": features.model_dump(),
            "allowed_chapters": allowed_chapters,
            "applied_gir_rules": gir_rules,
            "candidates": [c.model_dump() for c in candidates],
            "selected_gtip": None,
            "confidence_score": 0.0,
            "status": decision.status,
            "hitl_question": hitl_question.model_dump(),
            "audit_notes": decision.audit_notes,
        }
        local_state_store.save_state(session_id, state_dict)
        return decision

    def start_analysis(self, raw_text: str, image_uri: str = None) -> GTIPDecision:
        session_id = str(uuid.uuid4())
        stage_started = time.perf_counter()

        # DURUM 0: Varlık & Özellik Ayrıştırma (Gemini Flash-Lite)
        features = feature_extractor.extract_features(raw_text, image_uri)
        stage_started = _mark_pipeline_stage(session_id, "durum_0_feature_extraction", stage_started)

        # DURUM 2: Fasıl Belirleme & GYK 1 Elemesi (Negation Filter)
        allowed_chapters, gir_rules = rule_engine.apply_rules(features)
        allowed_chapters, exclusions = negation_engine.apply_negation_filter(allowed_chapters, features)
        for excl in exclusions:
            gir_rules.append(
                f"GYK 1 (Hariç Bırakma): {excl['legal_reference']} gereğince "
                f"Fasıl {excl['excluded_chapter']} elendi -> Fasıl {excl['redirect_chapter']} yönlendirildi."
            )
        stage_started = _mark_pipeline_stage(session_id, "durum_2_gyk1_negation", stage_started)

        # DURUM 1 & DURUM 5: Hiyerarşik Hibrit RAG Arama (AlloyDB ScaNN & RRF)
        tree_result = rag_engine.search_candidates_hierarchical(
            session_id, features, allowed_chapters, applied_gir_rules=gir_rules
        )
        stage_started = _mark_pipeline_stage(session_id, "durum_1_rag_retrieval", stage_started)
        if tree_result.discriminator_question:
            return self._pause_for_discriminator(
                session_id, raw_text, image_uri, features, allowed_chapters, gir_rules, tree_result
            )
        candidates = tree_result.candidates

        if not candidates:
            return GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                state_machine_stage="DURUM_1_EMPTY",
                audit_notes=["RAG uzayında uygun emsal karar bulunamadı. Kıdemli Müşavire yönlendirildi."]
            )

        # Hukuki kaynak otoritesi benzerlik skorundan üstündür. Aktif TGTC/GYK
        # dayanağı olmayan bir aday, BTB benzerliği ne kadar yüksek olursa olsun
        # otomatik karar akışına giremez.
        eligible_candidates = []
        evidence_failures = []
        for candidate in candidates:
            is_eligible, evidence_status, ordered_sources = validate_candidate_evidence(candidate)
            candidate.legal_sources = ordered_sources
            if is_eligible:
                eligible_candidates.append(candidate)
            else:
                evidence_failures.append(f"{candidate.gtip_code}: {evidence_status}")
        candidates = eligible_candidates
        if not candidates:
            return GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                state_machine_stage="DURUM_2_LEGAL_EVIDENCE_GATE",
                legal_validation_status="MISSING_NORMATIVE_EVIDENCE",
                audit_notes=[
                    "Aktif TGTC/GYK dayanağı bulunmayan adaylar otomatik karardan çıkarıldı.",
                    *evidence_failures[:5],
                ],
            )

        # BTB yalnızca destekleyici emsaldir. Fast exit yasaktır: her aday GYK,
        # yasal not, kapalı-aday seçimi ve bağımsız doğrulama katmanlarından geçer.
        fast_exit_candidate = None
        fast_exit_btb = None
        for c in candidates:
            for p in getattr(c, "precedents", []):
                if getattr(p, "similarity_score", 0.0) >= 0.92:
                    if not fast_exit_btb or p.similarity_score > fast_exit_btb.similarity_score:
                        fast_exit_btb = p
                        fast_exit_candidate = c

        if False and fast_exit_candidate and fast_exit_btb:  # legacy branch intentionally disabled
            logger.info("[Fast Exit] BTB Kararı %s benzerlik skoru %.4f >= 0.92. Doğrudan Durum 6'ya atlanıyor.", fast_exit_btb.btb_no, fast_exit_btb.similarity_score)
            decision = GTIPDecision(
                session_id=session_id,
                status="COMPLETED",
                gtip_code=fast_exit_candidate.gtip_code,
                confidence_score=round(float(fast_exit_btb.similarity_score), 4),
                official_statute_text=f"2026 TGTC {fast_exit_candidate.gtip_code}: {fast_exit_candidate.description}",
                llm_reasoning_commentary=f"Emsal BTB Kararı ({fast_exit_btb.btb_no}) ile yüksek anlamsal benzerlik (%{int(fast_exit_btb.similarity_score * 100)}) sağlandığı için Fast Exit işletildi.",
                legal_justification=fast_exit_btb.legal_justification or f"BTB Kararı No: {fast_exit_btb.btb_no}",
                applied_gir_rules=gir_rules + [f"GYK 1: {fast_exit_btb.btb_no} sayılı BTB emsali (Benzerlik: {fast_exit_btb.similarity_score:.2f}) ile doğrudan sınıflandırıldı."],
                precedent_btbs=[fast_exit_btb],
                legal_sources=fast_exit_candidate.legal_sources,
                consulted_sources=fast_exit_candidate.consulted_sources,
                state_machine_stage="DURUM_1_FAST_EXIT",
                audit_notes=[f"Durum 1 Fast Exit: {fast_exit_btb.btb_no} numaralı emsal ile doğrudan Durum 6'ya geçildi."]
            )
            # DURUM 6: MEVZUAT TEDBİR, DOĞRULAMA & ÇIKIŞ KALKANI (GUARDRAILS)
            target_gtip_digits = re.sub(r"\D", "", str(decision.gtip_code or ""))
            try:
                with SessionLocal() as db_session:
                    is_valid_leaf, _ = validate_leaf_gtip(db_session, target_gtip_digits)
                    if is_valid_leaf:
                        decision.guardrail_status = "VERIFIED_LEAF"
                    else:
                        decision.guardrail_status = "FALLBACK_SUBHEADING"
                        if len(target_gtip_digits) >= 6:
                            decision.gtip_code = f"{target_gtip_digits[:6]}.00.00.00"
                            decision.status = "MANUAL_REVIEW_REQUIRED"
                            decision.audit_notes.append("Foreign Key Barrier: Kod 12 haneli yaprak olarak doğrulanamadığı için 6 haneli alt pozisyona çekildi.")
            except Exception as ex_val:
                logger.warning("[Guardrail Barrier] Doğrulama istisnası: %s", ex_val)
                decision.guardrail_status = "UNCHECKED"

            decision.trade_measures = get_customs_trade_measures(decision.gtip_code)
            decision.state_machine_stage = "DURUM_6_COMPLETED"

            state_dict: Dict[str, Any] = {
                "session_id": session_id,
                "raw_text": raw_text,
                "image_uri": image_uri,
                "product_features": features.model_dump(),
                "allowed_chapters": allowed_chapters,
                "applied_gir_rules": decision.applied_gir_rules,
                "candidates": [c.model_dump() for c in candidates],
                "selected_gtip": decision.gtip_code,
                "confidence_score": decision.confidence_score,
                "status": decision.status,
                "official_statute_text": decision.official_statute_text,
                "llm_reasoning_commentary": decision.llm_reasoning_commentary,
                "hitl_question": None,
                "audit_notes": decision.audit_notes,
            }
            local_state_store.save_state(session_id, state_dict)
            return decision

        # DURUM 3: 4 Haneli Pozisyon Tespiti & GYK 3(a, b, c) Çatışma Çözücü
        candidate_headings = [{"heading": c.heading or c.gtip_code[:4], "candidate": c} for c in candidates]
        resolved_heading, gyk3_rules = rule_engine.resolve_gyk3_conflict(candidate_headings, features)
        if gyk3_rules:
            gir_rules.extend(gyk3_rules)
            if resolved_heading and "candidate" in resolved_heading:
                spec_h = resolved_heading["candidate"].heading
                candidates = sorted(candidates, key=lambda c: 0 if (c.heading == spec_h) else 1)
        stage_started = _mark_pipeline_stage(session_id, "durum_3_gyk3_conflict", stage_started)

        selected_index = _exact_locked_candidate_index(tree_result, candidates)
        selection_started = time.perf_counter()
        if selected_index is None:
            selection = llm_verifier.select_candidate(
                raw_text=raw_text,
                candidates=candidates,
                allowed_chapters=allowed_chapters,
                gir_rules=gir_rules,
            )
            if selection.status == CandidateSelectionStatus.INSUFFICIENT_INFORMATION and candidates:
                return self._pause_for_candidate_disambiguation(
                    session_id, raw_text, image_uri, features, allowed_chapters, gir_rules, candidates, selection
                )
            if selection.status != CandidateSelectionStatus.SELECT or not selection.selected_candidate_id:
                return GTIPDecision(
                    session_id=session_id,
                    status="MANUAL_REVIEW_REQUIRED",
                    confidence_score=0.0,
                    state_machine_stage="DURUM_3_DISAMBIGUATION",
                    audit_notes=(selection.reasoning_points + selection.missing_information)[:8],
                )
            selected_index = int(selection.selected_candidate_id[1:]) - 1
        stage_started = _mark_pipeline_stage(session_id, "candidate_selection", selection_started)
        if selected_index < 0 or selected_index >= min(5, len(candidates)):
            return GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                state_machine_stage="DURUM_3_CLOSED_SET_FAIL",
                audit_notes=["Kapalı aday kümesi dışında seçim reddedildi."],
            )
        top_candidate = candidates[selected_index]

        # DURUM 4: GYK 5 Ambalaj ve Muhafaza Kontrolü
        is_fitted_case, gyk5_justification = rule_engine.evaluate_gyk5_packaging(
            features, base_heading=top_candidate.heading or top_candidate.gtip_code[:4]
        )
        if is_fitted_case and gyk5_justification:
            gir_rules.append(gyk5_justification)
        stage_started = _mark_pipeline_stage(session_id, "durum_4_gyk5_packaging", stage_started)

        # 3.5. Aşama: Dinamik Kural Denetimi (gcp_architecture_report.md Bölüm 6 - Dynamic Rule Auditor)
        heading_code = top_candidate.heading or top_candidate.gtip_code[:4]
        rule_check = check_dynamic_gtip_rules(
            heading_code,
            features.technical_specifications,
            candidate_gtip=top_candidate.gtip_code,
        )
        stage_started = _mark_pipeline_stage(session_id, "dynamic_rule_audit", stage_started)
        if rule_check:
            if rule_check.get("status") == "FAILED":
                return GTIPDecision(
                    session_id=session_id,
                    status="MANUAL_REVIEW_REQUIRED",
                    gtip_code=top_candidate.gtip_code,
                    confidence_score=0.0,
                    applied_gir_rules=gir_rules,
                    legal_sources=top_candidate.legal_sources,
                    consulted_sources=top_candidate.consulted_sources,
                    state_machine_stage="DYNAMIC_RULE_FAILED",
                    audit_notes=[
                        "Dinamik tarife koşulu karşılanmadı: "
                        f"{rule_check['missing_parameter']}={rule_check['actual_value']} "
                        f"{rule_check['operator']} {rule_check['expected_value']}"
                    ],
                )
            opts = []
            for idx, o in enumerate(rule_check.get("options", [])):
                opt_id = o.get("id", f"OPT_{idx}")
                label = o.get("label", o.get("text", str(o)))
                opts.append(HITLOption(
                    option_id=opt_id,
                    text=label,
                    impact_data={rule_check["missing_parameter"]: _option_impact_value(o)}
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
                confidence_score=0.0,
                hitl_question=hitl_q,
                applied_gir_rules=gir_rules,
                precedent_btbs=top_candidate.precedents,
                legal_sources=top_candidate.legal_sources,
                consulted_sources=top_candidate.consulted_sources,
                state_machine_stage="DYNAMIC_RULE_HITL",
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
        chapter_note = next(
            (source.excerpt for source in top_candidate.legal_sources if source.source_type == "FASIL_NOTU"),
            "",
        )
        predicates = predicate_registry.get_predicates_for_gtip(
            top_candidate.gtip_code,
            top_candidate.description,
            chapter_note,
        )
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
            verification_results = llm_verifier.verify_tariff_candidate(
                raw_text=raw_text,
                candidate_gtip=top_candidate.gtip_code,
                heading_desc=top_candidate.description,
                chapter_notes=next(
                    (s.excerpt for s in top_candidate.legal_sources if s.source_type == "FASIL_NOTU"), "",
                ),
                gir_rules=gir_rules,
                evidence_context=evidence_context,
            )
        stage_started = _mark_pipeline_stage(session_id, "legal_predicate_verification", stage_started)

        # 5. Aşama: Deterministik Sembolik Karar Motoru (%5 Eşik Kuralı & No-AI Output Binding)
        decision = deterministic_engine.evaluate_decision(
            session_id=session_id,
            top_candidate=top_candidate,
            verification_results=verification_results,
            candidates=candidates
        )
        _mark_pipeline_stage(session_id, "deterministic_binding", stage_started)
        decision = _bind_legal_sources(decision, top_candidate)
        decision.legal_validation_status = "PASSED"

        # DURUM 6: MEVZUAT TEDBİR, DOĞRULAMA & ÇIKIŞ KALKANI (GUARDRAILS)
        target_gtip_digits = re.sub(r"\D", "", str(decision.gtip_code or ""))
        try:
            with SessionLocal() as db_session:
                is_valid_leaf, verified_record = validate_leaf_gtip(db_session, target_gtip_digits)
                if is_valid_leaf:
                    decision.guardrail_status = "VERIFIED_LEAF"
                else:
                    logger.warning("[Guardrail Barrier] %s 12 haneli yaprak kod olarak doğrulanamadı!", decision.gtip_code)
                    decision.guardrail_status = "FALLBACK_SUBHEADING"
                    if len(target_gtip_digits) >= 6:
                        decision.gtip_code = f"{target_gtip_digits[:6]}.00.00.00"
                        decision.status = "MANUAL_REVIEW_REQUIRED"
                        decision.audit_notes.append(
                            "Foreign Key Barrier: Kod 12 haneli yaprak olarak doğrulanamadığı için 6 haneli alt pozisyona çekildi."
                        )
        except Exception as ex_val:
            logger.warning("[Guardrail Barrier] Doğrulama istisnası: %s", ex_val)
            decision.guardrail_status = "UNCHECKED"

        decision.trade_measures = get_customs_trade_measures(decision.gtip_code)
        decision.state_machine_stage = "DURUM_6_COMPLETED"
        decision.applied_gir_rules = list(dict.fromkeys(gir_rules))

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
        stage_started = time.perf_counter()

        yield {
            "stage": "FEATURE_EXTRACTION",
            "status": "IN_PROGRESS",
            "message": "Aşama 1: Multimodal ürün nitelikleri ve teknik parametreler çıkarılıyor (Gemini 2.5 Flash)...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        features = await asyncio.to_thread(feature_extractor.extract_features, raw_text, image_uri)
        stage_started = _mark_pipeline_stage(session_id, "feature_extraction", stage_started)

        yield {
            "stage": "RULE_ENGINE",
            "status": "IN_PROGRESS",
            "message": f"Aşama 2: GİR Kuralları ve Fasıl Kilitleri işletiliyor (Baskın malzeme: {features.primary_material})...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        allowed_chapters, gir_rules = await asyncio.to_thread(rule_engine.apply_rules, features)
        allowed_chapters, exclusions = await asyncio.to_thread(negation_engine.apply_negation_filter, allowed_chapters, features)
        for excl in exclusions:
            gir_rules.append(
                f"GYK 1 (Hariç Bırakma): {excl['legal_reference']} gereğince "
                f"Fasıl {excl['excluded_chapter']} elendi -> Fasıl {excl['redirect_chapter']} yönlendirildi."
            )
        stage_started = _mark_pipeline_stage(session_id, "gir_routing", stage_started)

        yield {
            "stage": "RAG_SEARCH",
            "status": "IN_PROGRESS",
            "message": f"Aşama 3: Hiyerarşik Hibrit RAG (pgvector Dense + BM25 Sparse & RRF) taranıyor (Fasıllar: {allowed_chapters[:3]})...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        tree_result = await asyncio.to_thread(
            rag_engine.search_candidates_hierarchical,
            session_id, features, allowed_chapters, gir_rules,
        )
        stage_started = _mark_pipeline_stage(session_id, "hierarchical_retrieval", stage_started)
        if tree_result.discriminator_question:
            decision = self._pause_for_discriminator(
                session_id, raw_text, image_uri, features, allowed_chapters, gir_rules, tree_result
            )
            yield {
                "stage": "COMPLETED",
                "status": decision.status,
                "message": "Yakın skorlu tarife dalları için ayırt edici kullanıcı yanıtı gerekiyor.",
                "decision": decision.model_dump(),
            }
            return
        candidates = tree_result.candidates

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

        # SSE yolu da senkron akışla aynı hukuk kapısından geçer; emsal BTB
        # yalnız başına otomatik karar üretemez.
        eligible_candidates = []
        evidence_failures = []
        for candidate in candidates:
            is_eligible, evidence_status, ordered_sources = validate_candidate_evidence(candidate)
            candidate.legal_sources = ordered_sources
            if is_eligible:
                eligible_candidates.append(candidate)
            else:
                evidence_failures.append(f"{candidate.gtip_code}: {evidence_status}")
        candidates = eligible_candidates
        if not candidates:
            decision = GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                state_machine_stage="DURUM_2_LEGAL_EVIDENCE_GATE",
                legal_validation_status="MISSING_NORMATIVE_EVIDENCE",
                audit_notes=["Aktif TGTC/GYK dayanağı olmayan adaylar otomatik karardan çıkarıldı.", *evidence_failures[:5]],
            )
            yield {
                "stage": "COMPLETED",
                "status": decision.status,
                "message": "Aktif normatif dayanak olmadığı için uzman incelemesi gerekiyor.",
                "decision": decision.model_dump(),
            }
            return

        # BTB yalnızca destekleyici emsaldir; tüm adaylar doğrulama katmanına gider.
        fast_exit_candidate = None
        fast_exit_btb = None
        for c in candidates:
            for p in getattr(c, "precedents", []):
                if getattr(p, "similarity_score", 0.0) >= 0.92:
                    if not fast_exit_btb or p.similarity_score > fast_exit_btb.similarity_score:
                        fast_exit_btb = p
                        fast_exit_candidate = c

        if False and fast_exit_candidate and fast_exit_btb:  # legacy branch intentionally disabled
            logger.info("[Fast Exit Stream] BTB Kararı %s benzerlik skoru %.4f >= 0.92. Doğrudan Durum 6'ya atlanıyor.", fast_exit_btb.btb_no, fast_exit_btb.similarity_score)
            yield {
                "stage": "FAST_EXIT",
                "status": "IN_PROGRESS",
                "message": f"Yüksek benzerlikli emsal karar ({fast_exit_btb.btb_no}, skor: {fast_exit_btb.similarity_score:.2f}) tespit edildi, doğrudan mevzuat tedbirlerine geçiliyor...",
                "session_id": session_id
            }
            decision = GTIPDecision(
                session_id=session_id,
                status="COMPLETED",
                gtip_code=fast_exit_candidate.gtip_code,
                confidence_score=round(float(fast_exit_btb.similarity_score), 4),
                official_statute_text=f"2026 TGTC {fast_exit_candidate.gtip_code}: {fast_exit_candidate.description}",
                llm_reasoning_commentary=f"Emsal BTB Kararı ({fast_exit_btb.btb_no}) ile yüksek anlamsal benzerlik (%{int(fast_exit_btb.similarity_score * 100)}) sağlandığı için Fast Exit işletildi.",
                legal_justification=fast_exit_btb.legal_justification or f"BTB Kararı No: {fast_exit_btb.btb_no}",
                applied_gir_rules=gir_rules + [f"GYK 1: {fast_exit_btb.btb_no} sayılı BTB emsali (Benzerlik: {fast_exit_btb.similarity_score:.2f}) ile doğrudan sınıflandırıldı."],
                precedent_btbs=[fast_exit_btb],
                legal_sources=fast_exit_candidate.legal_sources,
                consulted_sources=fast_exit_candidate.consulted_sources,
                state_machine_stage="DURUM_1_FAST_EXIT",
                audit_notes=[f"Durum 1 Fast Exit: {fast_exit_btb.btb_no} numaralı emsal ile doğrudan Durum 6'ya geçildi."]
            )
            # DURUM 6: MEVZUAT TEDBİR, DOĞRULAMA & ÇIKIŞ KALKANI (GUARDRAILS)
            target_gtip_digits = re.sub(r"\D", "", str(decision.gtip_code or ""))
            try:
                with SessionLocal() as db_session:
                    is_valid_leaf, _ = validate_leaf_gtip(db_session, target_gtip_digits)
                    if is_valid_leaf:
                        decision.guardrail_status = "VERIFIED_LEAF"
                    else:
                        decision.guardrail_status = "FALLBACK_SUBHEADING"
                        if len(target_gtip_digits) >= 6:
                            decision.gtip_code = f"{target_gtip_digits[:6]}.00.00.00"
                            decision.status = "MANUAL_REVIEW_REQUIRED"
                            decision.audit_notes.append("Foreign Key Barrier: Kod 12 haneli yaprak olarak doğrulanamadığı için 6 haneli alt pozisyona çekildi.")
            except Exception as ex_val:
                logger.warning("[Guardrail Barrier] Doğrulama istisnası: %s", ex_val)
                decision.guardrail_status = "UNCHECKED"

            decision.trade_measures = get_customs_trade_measures(decision.gtip_code)
            decision.state_machine_stage = "DURUM_6_COMPLETED"

            state_dict: Dict[str, Any] = {
                "session_id": session_id,
                "raw_text": raw_text,
                "image_uri": image_uri,
                "product_features": features.model_dump(),
                "allowed_chapters": allowed_chapters,
                "applied_gir_rules": decision.applied_gir_rules,
                "candidates": [c.model_dump() for c in candidates],
                "selected_gtip": decision.gtip_code,
                "confidence_score": decision.confidence_score,
                "status": decision.status,
                "official_statute_text": decision.official_statute_text,
                "llm_reasoning_commentary": decision.llm_reasoning_commentary,
                "hitl_question": None,
                "audit_notes": decision.audit_notes,
            }
            local_state_store.save_state(session_id, state_dict)

            yield {
                "stage": "COMPLETED",
                "status": decision.status,
                "message": f"Analiz tamamlandı. GTİP Kodu: {decision.gtip_code} (Emsal BTB Fast Exit)",
                "decision": decision.model_dump()
            }
            return

        selected_index = _exact_locked_candidate_index(tree_result, candidates)
        selection_started = time.perf_counter()
        if selected_index is None:
            selection = await asyncio.to_thread(
                llm_verifier.select_candidate, raw_text, candidates, allowed_chapters, gir_rules
            )
            if selection.status == CandidateSelectionStatus.INSUFFICIENT_INFORMATION and candidates:
                decision = self._pause_for_candidate_disambiguation(
                    session_id, raw_text, image_uri, features, allowed_chapters, gir_rules, candidates, selection
                )
                yield {
                    "stage": "COMPLETED",
                    "status": decision.status,
                    "message": "Aday GTİP pozisyonunu kesinleştirmek için kullanıcı netleştirmesi bekleniyor.",
                    "decision": decision.model_dump(),
                }
                return
            if selection.status != CandidateSelectionStatus.SELECT or not selection.selected_candidate_id:
                decision = GTIPDecision(
                    session_id=session_id,
                    status="MANUAL_REVIEW_REQUIRED",
                    audit_notes=(selection.reasoning_points + selection.missing_information)[:8],
                )
                yield {
                    "stage": "COMPLETED",
                    "status": decision.status,
                    "message": "Kapalı aday kümesinde güvenilir seçim yapılamadı.",
                    "decision": decision.model_dump(),
                }
                return
            selected_index = int(selection.selected_candidate_id[1:]) - 1
        stage_started = _mark_pipeline_stage(session_id, "candidate_selection", selection_started)
        top_candidate = candidates[selected_index]

        rule_check = await asyncio.to_thread(
            check_dynamic_gtip_rules,
            top_candidate.heading or top_candidate.gtip_code[:4],
            features.technical_specifications,
            top_candidate.gtip_code,
        )
        stage_started = _mark_pipeline_stage(session_id, "dynamic_rule_audit", stage_started)
        if rule_check:
            if rule_check.get("status") == "FAILED":
                decision = GTIPDecision(
                    session_id=session_id,
                    status="MANUAL_REVIEW_REQUIRED",
                    gtip_code=top_candidate.gtip_code,
                    audit_notes=["Dinamik tarife koşulu karşılanmadı."],
                )
            else:
                options = [
                    HITLOption(
                        option_id=option.get("id", f"OPT_{index}"),
                        text=option.get("label", option.get("text", str(option))),
                        impact_data={rule_check["missing_parameter"]: _option_impact_value(option)},
                    )
                    for index, option in enumerate(rule_check.get("options", []))
                ]
                question = HITLQuestion(
                    question_id=f"q_{rule_check['missing_parameter']}_{session_id[:6]}",
                    question_text=rule_check["question"],
                    missing_parameter=rule_check["missing_parameter"],
                    options=options,
                )
                decision = GTIPDecision(
                    session_id=session_id,
                    status="WAITING_FOR_USER",
                    gtip_code=top_candidate.gtip_code,
                    hitl_question=question,
                    legal_sources=top_candidate.legal_sources,
                    consulted_sources=top_candidate.consulted_sources,
                )
                local_state_store.save_state(session_id, {
                    "session_id": session_id,
                    "raw_text": raw_text,
                    "image_uri": image_uri,
                    "product_features": features.model_dump(),
                    "allowed_chapters": allowed_chapters,
                    "applied_gir_rules": gir_rules,
                    "candidates": [candidate.model_dump() for candidate in candidates],
                    "selected_gtip": top_candidate.gtip_code,
                    "status": decision.status,
                    "hitl_question": question.model_dump(),
                })
            yield {
                "stage": "COMPLETED",
                "status": decision.status,
                "message": "Dinamik tarife kuralı için kullanıcı teyidi gerekiyor.",
                "decision": decision.model_dump(),
            }
            return

        yield {
            "stage": "LLM_VERIFICATION",
            "status": "IN_PROGRESS",
            "message": f"Aşama 4: Yasal dışlama ve yüklem doğrulayıcı çalışıyor (Aday: {top_candidate.gtip_code})...",
            "session_id": session_id
        }
        await asyncio.sleep(0.05)
        chapter_note = next(
            (source.excerpt for source in top_candidate.legal_sources if source.source_type == "FASIL_NOTU"), ""
        )
        predicates = await asyncio.to_thread(
            predicate_registry.get_predicates_for_gtip,
            top_candidate.gtip_code,
            top_candidate.description,
            chapter_note,
        )
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
                next((s.excerpt for s in top_candidate.legal_sources if s.source_type == "FASIL_NOTU"), ""),
                gir_rules,
                evidence_context,
            )
        stage_started = _mark_pipeline_stage(session_id, "legal_predicate_verification", stage_started)

        decision = await asyncio.to_thread(
            deterministic_engine.evaluate_decision, session_id, top_candidate, verification_results, candidates
        )
        _mark_pipeline_stage(session_id, "deterministic_binding", stage_started)
        decision = _bind_legal_sources(decision, top_candidate)
        decision.legal_validation_status = "PASSED"

        # Foreign Key Barrier ve Tedbir Kartları
        target_gtip_digits = re.sub(r"\D", "", str(decision.gtip_code or ""))
        try:
            with SessionLocal() as db_session:
                is_valid_leaf, _ = validate_leaf_gtip(db_session, target_gtip_digits)
                if is_valid_leaf:
                    decision.guardrail_status = "VERIFIED_LEAF"
                else:
                    decision.guardrail_status = "FALLBACK_SUBHEADING"
                    if len(target_gtip_digits) >= 6:
                        decision.gtip_code = f"{target_gtip_digits[:6]}.00.00.00"
                        decision.status = "MANUAL_REVIEW_REQUIRED"
                        decision.audit_notes.append("Foreign Key Barrier: Kod 6 haneli alt pozisyona çekildi.")
        except Exception:
            decision.guardrail_status = "UNCHECKED"

        decision.trade_measures = get_customs_trade_measures(decision.gtip_code)
        decision.state_machine_stage = "DURUM_6_COMPLETED"
        decision.applied_gir_rules = list(dict.fromkeys(gir_rules))

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
        resume_started = time.perf_counter()
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

        # Seçilen yanıt yalnızca sunucunun daha önce imzaladığı seçeneklerden gelir.
        selected_gtip_choice = None
        selected_impact: Dict[str, str] = {}
        selected_answer_text = ""
        if hitl_q and "options" in hitl_q:
            for opt in hitl_q["options"]:
                if opt["option_id"] == selected_option_id:
                    selected_answer_text = str(opt.get("text") or "").strip()
                    selected_impact = dict(opt.get("impact_data", {}))
                    if "selected_gtip" in selected_impact:
                        selected_gtip_choice = selected_impact["selected_gtip"]
                    feature_updates = {
                        key: value for key, value in selected_impact.items()
                        if key not in {"selected_gtip", "selected_branch", "predicate_verified"}
                    }
                    features.technical_specifications.update(feature_updates)
                    if "primary_material" in selected_impact:
                        features.primary_material = selected_impact["primary_material"]
                    missing_parameter = str(hitl_q.get("missing_parameter") or "").strip()
                    if missing_parameter and selected_answer_text:
                        # Ayırt edici cevap yalnız dal kilidi olarak kalmamalı. Son hukuki
                        # doğrulayıcıya kanıt olacak şekilde ürün özelliklerine de yazılır.
                        features.technical_specifications[missing_parameter] = selected_answer_text

        if selected_option_id == "UNKNOWN" or (not state_dict.get("discriminator_traversal") and not selected_gtip_choice and not state_dict.get("selected_gtip")):
            decision = GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                confidence_score=0.0,
                audit_notes=["Kullanıcı ayırt edici tarife bilgisini bilinmiyor olarak işaretledi. Gümrük Müşaviri incelemesi gerekiyor."],
            )
            state_dict.update({
                "status": decision.status,
                "hitl_question": None,
                "audit_notes": decision.audit_notes,
            })
            local_state_store.save_state(session_id, state_dict)
            return decision

        traversal = state_dict.get("discriminator_traversal")
        if traversal:
            selected_branch = str(selected_impact.get("selected_branch") or "")
            if not selected_branch:
                decision = GTIPDecision(
                    session_id=session_id,
                    status="MANUAL_REVIEW_REQUIRED",
                    confidence_score=0.0,
                    audit_notes=["Ayırt edici tarife bilgisi kullanıcı tarafından bilinmiyor olarak işaretlendi."],
                )
                state_dict.update({
                    "status": decision.status,
                    "hitl_question": None,
                    "audit_notes": decision.audit_notes,
                })
                local_state_store.save_state(session_id, state_dict)
                return decision

            pending_level = traversal.get("pending_level")
            locked_heading = traversal.get("locked_heading")
            locked_subheading = traversal.get("locked_subheading")
            locked_gtip = traversal.get("locked_gtip")
            if pending_level == "HEADING":
                locked_heading = selected_branch
                locked_subheading = None
                locked_gtip = None
            elif pending_level == "SUBHEADING":
                locked_subheading = selected_branch
                locked_gtip = None
            elif pending_level == "GTIP":
                locked_gtip = selected_branch

            retrieval_started = time.perf_counter()
            tree_result = rag_engine.search_candidates_hierarchical(
                session_id=session_id,
                features=features,
                allowed_chapters=traversal.get("retained_chapters") or state_dict.get("allowed_chapters") or [],
                applied_gir_rules=state_dict.get("applied_gir_rules") or [],
                locked_heading=locked_heading,
                locked_subheading=locked_subheading,
                locked_gtip=locked_gtip,
                query_vector=traversal.get("query_vector"),
            )
            _mark_pipeline_stage(session_id, "resume_hierarchical_retrieval", retrieval_started)
            if tree_result.discriminator_question:
                return self._pause_for_discriminator(
                    session_id,
                    state_dict.get("raw_text", ""),
                    state_dict.get("image_uri"),
                    features,
                    state_dict.get("allowed_chapters") or [],
                    state_dict.get("applied_gir_rules") or [],
                    tree_result,
                )
            if not tree_result.candidates:
                decision = GTIPDecision(
                    session_id=session_id,
                    status="MANUAL_REVIEW_REQUIRED",
                    confidence_score=0.0,
                    audit_notes=["Kilitlenen tarife dalı altında yürürlükte 12 haneli aday bulunamadı."],
                )
                state_dict.update({"status": decision.status, "hitl_question": None})
                local_state_store.save_state(session_id, state_dict)
                return decision

            locked_digits = re.sub(r"\D", "", str(locked_gtip or ""))
            exact_locked_candidates = [
                index for index, candidate in enumerate(tree_result.candidates)
                if re.sub(r"\D", "", candidate.gtip_code) == locked_digits
            ]
            if locked_digits and len(exact_locked_candidates) == 1:
                # Kullanıcı tarife ağacındaki ayırt edici sorularla tek bir yürürlükteki
                # 12 haneli yaprağı kilitledi. Aynı tek adayı LLM'ye yeniden seçtirmek
                # hem sonuç değiştiremez hem de bir tam model çağrısı kadar gecikme yaratır.
                selected_index = exact_locked_candidates[0]
            else:
                selection = llm_verifier.select_candidate(
                    state_dict.get("raw_text", ""), tree_result.candidates,
                    state_dict.get("allowed_chapters") or [],
                    state_dict.get("applied_gir_rules") or [],
                )
                if selection.status != CandidateSelectionStatus.SELECT or not selection.selected_candidate_id:
                    return GTIPDecision(
                        session_id=session_id,
                        status="MANUAL_REVIEW_REQUIRED",
                        confidence_score=0.0,
                        audit_notes=(selection.reasoning_points + selection.missing_information)[:8],
                    )
                selected_index = int(selection.selected_candidate_id[1:]) - 1
            if selected_index < 0 or selected_index >= len(tree_result.candidates):
                raise LookupError("Kilitlenen dal dışında aday seçimi reddedildi.")
            stored_candidates = tree_result.candidates
            selected_gtip_choice = stored_candidates[selected_index].gtip_code
            state_dict["candidates"] = [candidate.model_dump() for candidate in stored_candidates]
            state_dict["discriminator_traversal"] = None

        selected_gtip = selected_gtip_choice or state_dict.get("selected_gtip")
        stored_candidates_data = state_dict.get("candidates", [])
        if not traversal:
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
            selection = llm_verifier.select_candidate(
                state_dict.get("raw_text", ""), candidates, allowed_chapters, gir_rules
            )
            if selection.status != CandidateSelectionStatus.SELECT or not selection.selected_candidate_id:
                return GTIPDecision(
                    session_id=session_id,
                    status="MANUAL_REVIEW_REQUIRED",
                    audit_notes=(selection.reasoning_points + selection.missing_information)[:8],
                )
            top_candidate = candidates[int(selection.selected_candidate_id[1:]) - 1]
            stored_candidates = candidates

        if selected_impact.get("predicate_verified") == "FALSE" or selected_option_id == "OPT_NO":
            decision = GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                gtip_code=top_candidate.gtip_code,
                confidence_score=0.0,
                legal_sources=top_candidate.legal_sources,
                consulted_sources=top_candidate.consulted_sources,
                audit_notes=["Kullanıcı zorunlu yasal/teknik koşulu olumsuz yanıtladı; otomatik onay engellendi."],
            )
            state_dict["status"] = decision.status
            state_dict["product_features"] = features.model_dump()
            state_dict["hitl_question"] = None
            state_dict["audit_notes"] = decision.audit_notes
            local_state_store.save_state(session_id, state_dict)
            return decision

        # Teknik seçenek yanıtlandıktan sonra bütün dinamik kurallar tekrar çalışır.
        rule_check = check_dynamic_gtip_rules(
            top_candidate.heading or top_candidate.gtip_code[:4],
            features.technical_specifications,
            candidate_gtip=top_candidate.gtip_code,
        )
        if rule_check and rule_check.get("status") == "MISSING":
            options = [
                HITLOption(
                    option_id=option.get("id", f"OPT_{index}"),
                    text=option.get("label", option.get("text", str(option))),
                    impact_data={rule_check["missing_parameter"]: _option_impact_value(option)},
                )
                for index, option in enumerate(rule_check.get("options", []))
            ]
            next_question = HITLQuestion(
                question_id=f"q_{rule_check['missing_parameter']}_{session_id[:6]}",
                question_text=rule_check["question"],
                missing_parameter=rule_check["missing_parameter"],
                options=options,
            )
            decision = GTIPDecision(
                session_id=session_id,
                status="WAITING_FOR_USER",
                gtip_code=top_candidate.gtip_code,
                confidence_score=0.0,
                hitl_question=next_question,
                applied_gir_rules=gir_rules,
                precedent_btbs=top_candidate.precedents,
                legal_sources=top_candidate.legal_sources,
                consulted_sources=top_candidate.consulted_sources,
                audit_notes=[f"Sıradaki zorunlu teknik parametre bekleniyor: {rule_check['missing_parameter']}"],
            )
            state_dict["status"] = decision.status
            state_dict["product_features"] = features.model_dump()
            state_dict["hitl_question"] = next_question.model_dump()
            state_dict["selected_gtip"] = top_candidate.gtip_code
            local_state_store.save_state(session_id, state_dict)
            return decision

        if rule_check and rule_check.get("status") == "FAILED":
            decision = GTIPDecision(
                session_id=session_id,
                status="MANUAL_REVIEW_REQUIRED",
                gtip_code=top_candidate.gtip_code,
                confidence_score=0.0,
                legal_sources=top_candidate.legal_sources,
                consulted_sources=top_candidate.consulted_sources,
                audit_notes=[f"Yanıtlanan teknik değer seçilen GTİP koşulunu karşılamıyor: {rule_check}"],
            )
            state_dict["status"] = decision.status
            state_dict["product_features"] = features.model_dump()
            state_dict["hitl_question"] = None
            state_dict["audit_notes"] = decision.audit_notes
            local_state_store.save_state(session_id, state_dict)
            return decision

        raw_text = state_dict.get("raw_text", "")
        verified_product_text = raw_text
        if features.technical_specifications:
            verified_product_text += (
                "\nKullanıcının ayırt edici sorulara verdiği doğrulanmış teknik cevaplar: "
                + json.dumps(features.technical_specifications, ensure_ascii=False, sort_keys=True)
            )
        chapter_note = next(
            (source.excerpt for source in top_candidate.legal_sources if source.source_type == "FASIL_NOTU"), ""
        )
        predicates = predicate_registry.get_predicates_for_gtip(
            top_candidate.gtip_code,
            top_candidate.description,
            chapter_note,
        )
        evidence_context = _format_evidence_context(top_candidate)
        verification_started = time.perf_counter()
        verification_results = llm_verifier.verify_predicates(
            raw_text=verified_product_text,
            predicates=predicates,
            allowed_chapters=allowed_chapters,
            evidence_context=evidence_context,
        )
        _mark_pipeline_stage(session_id, "resume_legal_predicate_verification", verification_started)
        predicate_answer = selected_impact.get("predicate_verified")
        answered_predicate = hitl_q.get("missing_parameter")
        if predicate_answer in {"TRUE", "FALSE"}:
            for result in verification_results:
                if result.predicate_id == answered_predicate:
                    result.status = PredicateStatus(predicate_answer)

        evaluation_candidates = [top_candidate] if selected_gtip_choice else stored_candidates
        decision = deterministic_engine.evaluate_decision(
            session_id, top_candidate, verification_results, evaluation_candidates
        )
        decision = _bind_legal_sources(decision, top_candidate)
        _mark_pipeline_stage(session_id, "resume_total", resume_started)

        state_dict["status"] = decision.status
        state_dict["product_features"] = features.model_dump()
        state_dict["hitl_question"] = decision.hitl_question.model_dump() if decision.hitl_question else None
        state_dict["audit_notes"] = decision.audit_notes
        state_dict["confidence_score"] = decision.confidence_score
        state_dict["selected_gtip"] = top_candidate.gtip_code
        state_dict["official_statute_text"] = decision.official_statute_text
        state_dict["llm_reasoning_commentary"] = decision.llm_reasoning_commentary
        local_state_store.save_state(session_id, state_dict)
        return decision

workflow_engine = GTIPWorkflowEngine()

# ==============================================================================
# LANGGRAPH İŞ AKIŞI STANDARDI (gcp_architecture_report.md Bölüm 6)
# ==============================================================================

def feature_extractor_node(state: CustomsState):
    """Ana özellik çıkarıcıyı kullanır; örnek/sabit pozisyon üretmez."""
    features = feature_extractor.extract_features(state.get("user_query", ""))
    return {
        "product_specs": features.technical_specifications,
        "candidate_heading": None,
        "status": "IN_PROGRESS",
    }

def dynamic_rule_auditor_node(state: CustomsState, session=None):
    """AlloyDB / Cloud SQL gtip_rules tablosundaki eşik şartlarını denetler."""
    heading = state.get("candidate_heading")
    if not heading:
        return {"status": "RESOLVED"}
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
    """Sabit örnek kod yerine üretimde kullanılan fail-closed karar hattına bağlanır."""
    decision = workflow_engine.start_analysis(state.get("user_query", ""))
    return {
        "final_gtip": decision.gtip_code,
        "legal_basis": {
            "official_statute_text": decision.official_statute_text,
            "legal_sources": [source.model_dump() for source in decision.legal_sources],
        },
        "status": decision.status,
        "audit_notes": decision.audit_notes,
    }

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
