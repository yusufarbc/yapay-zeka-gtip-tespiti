"""Minimal closed-set TGTC classification workflow.

Gemini chooses a path through server-provided official tariff nodes. It never
writes a GTIP code. The server resolves the returned option id, preserves the
parent/child path and accepts a result only when the selected 12-digit code is
an active database leaf.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from api.db.database import SessionLocal, validate_leaf_gtip
from api.db.gcp_emulator import local_state_store
from api.modules.discriminator_engine import DiscriminatorQuestion
from api.modules.feature_extractor import feature_extractor
from api.modules.rag_engine import HierarchicalSearchResult, rag_engine
from api.schemas.product import GTIPCandidate, GTIPDecision, HITLOption, HITLQuestion, LegalSource, PrecedentBTB, ProductFeatures


logger = logging.getLogger("GTIPWorkflowEngine")


def _format_gtip_code(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 12:
        return f"{digits[:4]}.{digits[4:6]}.{digits[6:8]}.{digits[8:10]}.{digits[10:12]}"
    return digits


def get_customs_trade_measures(gtip_code: Optional[str]) -> Dict[str, Any]:
    """Return the current UI measure summary for a verified code."""
    clean = re.sub(r"\D", "", str(gtip_code or ""))
    chapter = clean[:2] if len(clean) >= 2 else ""
    additional_duty = 20.0 if chapter in {"85", "84", "64", "39", "94", "73"} else 0.0
    tareks = "Tüketici Güvenliği ve Denetimi Tebliği" if chapter in {"85", "84", "95", "90"} else None
    surveillance = "İthalatta Gözetim Uygulanmasına İlişkin Tebliğ" if chapter in {"85", "64", "73"} else None
    return {
        "kdv_rate": 20.0,
        "additional_duty_rate": additional_duty,
        "tareks_required": tareks is not None,
        "tareks_detail": tareks,
        "surveillance_measure": surveillance,
    }


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


class GTIPWorkflowEngine:
    """Model traversal plus deterministic anti-hallucination barriers."""

    @staticmethod
    def _manual_review(
        session_id: str,
        note: str,
        stage: str,
        gtip_code: Optional[str] = None,
    ) -> GTIPDecision:
        return GTIPDecision(
            session_id=session_id,
            status="MANUAL_REVIEW_REQUIRED",
            gtip_code=gtip_code,
            confidence_score=0.0,
            state_machine_stage=stage,
            audit_notes=[note],
        )

    def _pause(
        self,
        session_id: str,
        raw_text: str,
        image_uri: Optional[str],
        features: ProductFeatures,
        tree_result: Any,
    ) -> GTIPDecision:
        question = _as_hitl_question(tree_result.discriminator_question)
        traversal = dict(tree_result.traversal_state or {})
        decision = GTIPDecision(
            session_id=session_id,
            status="WAITING_FOR_USER",
            gtip_code=None,
            confidence_score=0.0,
            official_statute_text=None,
            consulted_sources=["BTB", "TGTC_2026"],
            hitl_question=question,
            state_machine_stage=f"MODEL_{traversal.get('pending_level', 'TARIFF')}_QUESTION",
            audit_notes=[
                "Gemini kesin seçim için eksik bilgi belirledi; seçenekler yalnız resmi kardeş tarife düğümleridir."
            ],
        )
        local_state_store.save_state(session_id, {
            "session_id": session_id,
            "routing_mode": "MODEL_CLOSED_SET",
            "raw_text": raw_text,
            "image_uri": image_uri,
            "product_features": features.model_dump(),
            "allowed_chapters": list(traversal.get("retained_chapters") or []),
            "status": decision.status,
            "hitl_question": question.model_dump(),
            "discriminator_traversal": traversal,
            "audit_notes": decision.audit_notes,
        })
        return decision

    def _complete(
        self,
        session_id: str,
        raw_text: str,
        image_uri: Optional[str],
        features: ProductFeatures,
        tree_result: Any,
    ) -> GTIPDecision:
        traversal = dict(tree_result.traversal_state or {})
        locked_digits = re.sub(r"\D", "", str(traversal.get("locked_gtip") or ""))
        candidate: Optional[GTIPCandidate] = next(
            (
                item for item in tree_result.candidates
                if re.sub(r"\D", "", str(item.gtip_code)) == locked_digits
            ),
            None,
        )
        if not candidate or len(locked_digits) != 12:
            return self._manual_review(
                session_id,
                "Model seçimi sunucunun resmi kapalı yaprak kümesine bağlanamadı.",
                "MODEL_BINDING_FAILED",
            )

        try:
            with SessionLocal() as db_session:
                is_valid_leaf, verified_record = validate_leaf_gtip(db_session, locked_digits)
        except Exception as exc:
            logger.exception("GTIP leaf validation failed")
            return self._manual_review(
                session_id,
                f"Yürürlükteki GTİP yaprak kaydı doğrulanamadı: {exc}",
                "DATABASE_VALIDATION_ERROR",
            )
        if not is_valid_leaf:
            decision = self._manual_review(
                session_id,
                "Seçilen kod yürürlükteki TGTC veritabanında 12 haneli yaprak değildir.",
                "DATABASE_LEAF_REJECTED",
                _format_gtip_code(locked_digits),
            )
            decision.guardrail_status = "REJECTED_NON_LEAF"
            return decision

        formatted_code = _format_gtip_code(locked_digits)
        description = str((verified_record or {}).get("description") or candidate.description)
        stored_precedents = [
            PrecedentBTB(**item)
            for item in traversal.get("btb_precedents", [])
            if _format_gtip_code(item.get("gtip_code")) == _format_gtip_code(locked_digits)
        ][:3]
        precedents = list(candidate.precedents or stored_precedents)

        # EBTI emsalleri: traversal state'den al; CN-8 kodu ile filtreleme yap
        from api.schemas.product import PrecedentEBTI
        raw_ebti = traversal.get("ebti_precedents") or []
        ebti_precedents: List[PrecedentBTB] = []
        for item in raw_ebti:
            try:
                ep = PrecedentEBTI(**item)
                # CN-8 eşleşmesi kontrolü: Türk GTİP ilk 8 hanesi == EBTI CN-8
                if not ep.cn_code or locked_digits[:8] == ep.cn_code:
                    ebti_precedents.append(ep)
                elif not locked_digits:
                    ebti_precedents.append(ep)
            except Exception:
                pass
        ebti_precedents = ebti_precedents[:3]

        selection_source = traversal.get("selection_source")
        is_exact_btb = selection_source == "BTB_EXACT"
        has_ebti = len(ebti_precedents) > 0

        # Danışılan kaynaklar listesi
        consulted = list(dict.fromkeys(candidate.consulted_sources + ["BTB", "TGTC_2026", "GIR_1_6"]))
        if has_ebti:
            consulted = list(dict.fromkeys(consulted + ["EU_EBTI"]))

        # EBTI emsalleri varsa legal_sources'a da ekle
        ebti_legal_sources = [
            LegalSource(
                source_type="EU_EBTI",
                reference_no=ep.reference_no,
                title=f"AB EBTI {ep.reference_no} ({ep.country})",
                publication_date=ep.issue_date or None,
                excerpt=ep.product_description[:300],
                source_url=ep.source_url,
                legal_role="INDIVIDUAL_PRECEDENT",
                authority_level=4,
                is_binding=False,
            )
            for ep in ebti_precedents
        ] if has_ebti else []

        decision = GTIPDecision(
            session_id=session_id,
            status="COMPLETED",
            gtip_code=formatted_code,
            confidence_score=0.90,
            official_statute_text=f"2026 TGTC {formatted_code}: {description}",
            llm_reasoning_commentary=(
                "Ürün açıklaması gerçek BTB havuzundaki emsal kararla tam eşleşti; BTB kodu "
                "yürürlükteki TGTC veritabanında aktif 12 haneli yaprak olarak doğrulandı."
                if is_exact_btb
                else "Gemini resmi TGTC ağacındaki seçenek kimliklerini seçti; kod sunucu tarafından "
                "kapalı kümeye ve yürürlükteki veritabanı yaprağına bağlandı."
            ),
            legal_justification=(
                f"Tam ürün eşleşmeli emsal BTB ve güncel TGTC yaprak doğrulaması: {formatted_code}."
                if is_exact_btb
                else f"GİR 1 ve GİR 6 kapsamında resmi TGTC yaprak seçimi: {formatted_code}."
            ),
            applied_gir_rules=[
                "GİR 1: Resmi fasıl ve pozisyon metinleri arasında model seçimi.",
                "GİR 6: Aynı üst düğümdeki resmi alt pozisyonların karşılaştırılması.",
            ],
            precedent_btbs=precedents,
            precedent_ebtis=ebti_precedents,
            legal_sources=candidate.legal_sources + ebti_legal_sources,
            consulted_sources=consulted,
            trade_measures=get_customs_trade_measures(formatted_code),
            state_machine_stage="MODEL_CLOSED_SET_COMPLETED",
            guardrail_status="VERIFIED_LEAF",
            legal_validation_status="PASSED",
            audit_notes=[
                (
                    "Kod, tam eşleşen gerçek BTB emsalinden alındı; model GTİP kodu üretmedi."
                    if is_exact_btb
                    else "Model serbest GTİP kodu üretmedi; yalnız sunulan seçenek kimliğini seçti."
                ),
                "Kod, ebeveyn yolu, 12 haneli yaprak ve yürürlük durumu sunucuda doğrulandı.",
                *(
                    [f"AB EBTI emsali bulundu: {len(ebti_precedents)} karar (CN-8 uyumu ile)."]
                    if has_ebti else []
                ),
            ],
        )
        local_state_store.save_state(session_id, {
            "session_id": session_id,
            "routing_mode": "MODEL_CLOSED_SET",
            "raw_text": raw_text,
            "image_uri": image_uri,
            "product_features": features.model_dump(),
            "allowed_chapters": [locked_digits[:2]],
            "status": decision.status,
            "selected_gtip": formatted_code,
            "confidence_score": decision.confidence_score,
            "hitl_question": None,
            "discriminator_traversal": traversal,
            "audit_notes": decision.audit_notes,
        })
        return decision

    @staticmethod
    def _search(
        session_id: str,
        features: ProductFeatures,
        *,
        locked_chapter: Optional[str] = None,
        locked_heading: Optional[str] = None,
        locked_subheading: Optional[str] = None,
        locked_gtip: Optional[str] = None,
        query_vector: Optional[List[float]] = None,
    ) -> Any:
        return rag_engine.search_candidates_hierarchical(
            session_id=session_id,
            features=features,
            allowed_chapters=[locked_chapter] if locked_chapter else [],
            applied_gir_rules=[],
            locked_chapter=locked_chapter,
            locked_heading=locked_heading,
            locked_subheading=locked_subheading,
            locked_gtip=locked_gtip,
            query_vector=query_vector,
        )

    def start_analysis(self, raw_text: str, image_uri: str = None) -> GTIPDecision:
        session_id = str(uuid.uuid4())
        started = time.perf_counter()
        features = feature_extractor.extract_features(raw_text, image_uri)
        btb_precedents = rag_engine.search_btb_precedents(raw_text)
        # EBTI araması: BTB aramasından bağımsız çalışır, hata durumunda boş liste döner
        try:
            ebti_precedents = rag_engine.search_ebti_precedents(raw_text)
        except Exception as exc_ebti:
            logger.warning("EBTI emsal araması atlandı: %s", exc_ebti)
            ebti_precedents = []
        exact_btb = rag_engine.exact_btb_candidate(btb_precedents)
        if exact_btb:
            tree_result = HierarchicalSearchResult(
                candidates=[exact_btb],
                traversal_state={
                    "locked_chapter": exact_btb.chapter,
                    "locked_heading": exact_btb.heading,
                    "locked_subheading": _format_gtip_code(exact_btb.gtip_code).replace(".", "")[:6],
                    "locked_gtip": _format_gtip_code(exact_btb.gtip_code).replace(".", ""),
                    "selection_source": "BTB_EXACT",
                    "btb_precedents": [item.model_dump() for item in btb_precedents],
                    "ebti_precedents": [item.model_dump() for item in ebti_precedents],
                },
            )
        else:
            tree_result = self._search(session_id, features)
            tree_result.traversal_state["btb_precedents"] = [
                item.model_dump() for item in btb_precedents
            ]
            tree_result.traversal_state["ebti_precedents"] = [
                item.model_dump() for item in ebti_precedents
            ]
        logger.info(
            "[PipelineTiming] session=%s stage=model_closed_set duration_ms=%.2f btb_hits=%d ebti_hits=%d",
            session_id,
            (time.perf_counter() - started) * 1000,
            len(btb_precedents),
            len(ebti_precedents),
        )
        if tree_result.discriminator_question:
            return self._pause(session_id, raw_text, image_uri, features, tree_result)
        return self._complete(session_id, raw_text, image_uri, features, tree_result)


    async def start_analysis_async(self, raw_text: str, image_uri: str = None) -> GTIPDecision:
        return await asyncio.to_thread(self.start_analysis, raw_text, image_uri)

    async def start_analysis_stream(
        self,
        raw_text: str,
        image_uri: str = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        yield {
            "stage": "MODEL_TARIFF_SELECTION",
            "status": "IN_PROGRESS",
            "message": "Gemini resmi TGTC ağacında fasıl, pozisyon ve alt pozisyon seçiyor.",
        }
        decision = await self.start_analysis_async(raw_text, image_uri)
        yield {
            "stage": "COMPLETED",
            "status": decision.status,
            "message": "Kapalı-küme tarife seçimi tamamlandı.",
            "decision": decision.model_dump(),
        }

    def resume_analysis(
        self,
        session_id: str,
        selected_option_id: str,
        question_id: Optional[str] = None,
    ) -> GTIPDecision:
        state = local_state_store.get_state(session_id)
        if not state:
            raise ValueError(f"Oturum bulunamadı: {session_id}")
        question = state.get("hitl_question") or {}
        if state.get("status") != "WAITING_FOR_USER" or not question:
            raise LookupError("Bu oturum yanıt beklemiyor.")
        if question_id is not None and question_id != question.get("question_id"):
            raise LookupError("Yanıtlanan soru güncel değil.")
        option = next(
            (item for item in question.get("options", []) if item.get("option_id") == selected_option_id),
            None,
        )
        if not option:
            raise LookupError("Seçilen yanıt güncel soru seçenekleri arasında değil.")
        selected_branch = str((option.get("impact_data") or {}).get("selected_branch") or "")
        if not selected_branch:
            decision = self._manual_review(
                session_id,
                "Kullanıcı gerekli teknik ayrımı bilmiyor olarak işaretledi.",
                "USER_INFORMATION_MISSING",
            )
            state.update({"status": decision.status, "hitl_question": None})
            local_state_store.save_state(session_id, state)
            return decision

        traversal = dict(state.get("discriminator_traversal") or {})
        pending_level = traversal.get("pending_level")
        locked_chapter = traversal.get("locked_chapter")
        locked_heading = traversal.get("locked_heading")
        locked_subheading = traversal.get("locked_subheading")
        locked_gtip = traversal.get("locked_gtip")
        selected_digits = re.sub(r"\D", "", selected_branch)
        if pending_level == "CHAPTER":
            locked_chapter, locked_heading, locked_subheading, locked_gtip = selected_digits, None, None, None
        elif pending_level == "HEADING":
            locked_chapter, locked_heading, locked_subheading, locked_gtip = selected_digits[:2], selected_digits, None, None
        elif pending_level == "SUBHEADING":
            locked_subheading, locked_gtip = selected_digits, None
        elif pending_level == "GTIP":
            locked_gtip, locked_subheading = selected_digits, selected_digits[:6]
        else:
            raise LookupError("Tarife ağacındaki bekleyen seviye geçersiz.")

        features = ProductFeatures(**state.get("product_features", {}))
        tree_result = self._search(
            session_id,
            features,
            locked_chapter=locked_chapter,
            locked_heading=locked_heading,
            locked_subheading=locked_subheading,
            locked_gtip=locked_gtip,
            query_vector=traversal.get("query_vector"),
        )
        tree_result.traversal_state["btb_precedents"] = list(
            traversal.get("btb_precedents") or []
        )
        if tree_result.discriminator_question:
            return self._pause(
                session_id,
                state.get("raw_text", ""),
                state.get("image_uri"),
                features,
                tree_result,
            )
        return self._complete(
            session_id,
            state.get("raw_text", ""),
            state.get("image_uri"),
            features,
            tree_result,
        )


workflow_engine = GTIPWorkflowEngine()
