"""Minimal closed-set TGTC classification workflow.

Gemini chooses a path through server-provided official tariff nodes. It never
writes a GTIP code. The server resolves the returned option id, preserves the
parent/child path and accepts a result only when the selected 12-digit code is
an active database leaf.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from api.config import settings
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


def _record_run(
    session_id: str,
    raw_text: str,
    features: Optional[ProductFeatures],
    traversal: Dict[str, Any],
    decision: GTIPDecision,
) -> None:
    """Kararı değişmez bir çalışma kaydı olarak saklar.

    Denetim logu yalnız COMPLETED kararları tutuyordu ve ürün tanımını 50
    karaktere kesiyordu; sistemin başarısız olduğu vakalar hiç görünmüyor,
    görünenler de yeniden üretilemiyordu. `classification_run` tablosu tam bu iş
    için tanımlanmış ama hiç yazılmamıştı.

    Yazma hatası karar akışını bloke etmez: denetim kaydı kullanıcıya dönen
    sonucu düşürecek kadar kritik değildir.
    """
    try:
        from api.db.database import ClassificationRunModel

        with SessionLocal() as db_session:
            db_session.add(ClassificationRunModel(
                session_id=session_id,
                query_text=str(raw_text or ""),          # TAM metin, kesilmeden
                extracted_facts=features.model_dump_json() if features else "{}",
                candidate_codes=json.dumps(traversal, ensure_ascii=False, default=str),
                selected_gtip=re.sub(r"\D", "", str(decision.gtip_code or "")) or None,
                status=decision.status,                   # başarısızlıklar dahil
                confidence_score=decision.confidence_score,
                tariff_year=decision.tariff_year,
                model_version=settings.REASONING_LLM_MODEL,
            ))
            db_session.commit()
    except Exception:
        logger.exception("classification_run kaydı yazılamadı (session=%s)", session_id)


def compute_confidence(
    traversal: Dict[str, Any],
    precedents: List[Any],
    ebti_precedents: List[Any],
) -> float:
    """Kararın gerçek kanıt durumundan bir güven skoru türetir.

    Önceden her karar sabit 0.90 dönüyordu: arayüzdeki "%90 güven" hiçbir şey
    ölçmüyordu, `settings.CONFIDENCE_THRESHOLD` hiç okunmuyordu ve modelin emin
    olup yanıldığı durumlarda hiçbir fren yoktu.

    Sinyaller, kapalı-küme mimarisinin kendi güvencelerini yansıtır: kod her
    durumda sunucuda doğrulanmış aktif bir yapraktır (taban), üstüne emsal
    desteği ve gerekçelendirme eklenir, zayıf seçim düşülür.
    """
    # Birebir eşleşen BTB emsali: kodu model değil, idarenin kendi kararı verdi.
    if traversal.get("selection_source") == "BTB_EXACT":
        return 0.97

    # Taban: kapalı küme + ebeveyn yolu + aktif 12 haneli yaprak doğrulaması.
    score = 0.55

    best_btb = max((float(getattr(p_, "similarity_score", 0.0) or 0.0) for p_ in precedents), default=0.0)
    best_ebti = max((float(getattr(p_, "similarity_score", 0.0) or 0.0) for p_ in ebti_precedents), default=0.0)
    # BTB ulusal emsaldir, EBTI yalnız CN-8 düzeyinde yol gösterir.
    score += min(0.22, 0.22 * best_btb)
    score += min(0.08, 0.08 * best_ebti)

    # Model kararını resmî bir yorum kuralına bağladıysa izlenebilirlik artar.
    if traversal.get("applied_gir_keys"):
        score += 0.05
    # Müşavir teknik ayrımı bizzat yanıtladıysa belirsizlik giderilmiştir.
    if traversal.get("hitl_answer_count"):
        score += 0.08
    # Model hiçbir özel dalı eşleştiremedi, kalan tek "diğerleri" dalına düşüldü.
    if traversal.get("used_residual_fallback"):
        score -= 0.25
    # İlk fasıl seçimi hiçbir pozisyonla eşleşmedi ve geri alındı. Varılan sonuç
    # doğru olabilir ama modelin ilk kararı yanlıştı; bu zayıf bir kanıt durumudur
    # ve otomatik onaydan uzak tutulmalıdır.
    if traversal.get("used_chapter_backtrack"):
        score -= 0.15

    return round(max(0.0, min(0.99, score)), 3)


def _restore_precedents(traversal: Dict[str, Any]) -> List[Any]:
    """HITL devamında emsalleri oturum durumundan yeniden kurar.

    Devam eden oturumda emsaller yeniden aranmaz; ilk analizde bulunanlar
    saklanır. Aksi halde aynı ürün için HITL'li ve HITL'siz yol farklı delille
    karar verirdi.
    """
    from api.schemas.product import PrecedentEBTI

    restored: List[Any] = []
    for raw in traversal.get("btb_precedents") or []:
        try:
            restored.append(PrecedentBTB(**raw))
        except Exception:
            continue
    for raw in traversal.get("ebti_precedents") or []:
        try:
            restored.append(PrecedentEBTI(**raw))
        except Exception:
            continue
    return restored


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
        *,
        raw_text: str = "",
        features: Optional[ProductFeatures] = None,
        traversal: Optional[Dict[str, Any]] = None,
    ) -> GTIPDecision:
        decision = GTIPDecision(
            session_id=session_id,
            status="MANUAL_REVIEW_REQUIRED",
            gtip_code=gtip_code,
            confidence_score=0.0,
            state_machine_stage=stage,
            audit_notes=[note],
        )
        # Başarısızlıklar da kaydedilir: en çok iyileştirme bu vakalardan çıkar.
        _record_run(session_id, raw_text, features, traversal or {}, decision)
        return decision

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
                raw_text=raw_text, features=features, traversal=traversal,
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
                raw_text=raw_text, features=features, traversal=traversal,
            )
        if not is_valid_leaf:
            decision = self._manual_review(
                session_id,
                "Seçilen kod yürürlükteki TGTC veritabanında 12 haneli yaprak değildir.",
                "DATABASE_LEAF_REJECTED",
                _format_gtip_code(locked_digits),
                raw_text=raw_text, features=features, traversal=traversal,
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

        # Uluslararası Emsaller (ABD CBP CROSS / CustomsMobile, Çin GACC, AB EBTI)
        from api.schemas.product import InternationalRuling
        raw_intl = traversal.get("international_rulings") or []
        # Grounding'li canlı arama yavaştır (GROUNDED_SEARCH_TIMEOUT_MS). Yerel emsal
        # yokluğunda örtük tetiklemek her belirsiz üründe sıcak yola on saniyeler
        # ekliyordu; yalnız kullanıcı açıkça istediğinde çalıştırılır.
        if not raw_intl and traversal.get("enable_international_research"):
            try:
                from api.modules.international_search import search_international_rulings
                found_intl = search_international_rulings(
                    product_text=raw_text,
                    hs_code_hint=locked_digits[:6] if locked_digits else None,
                )
                raw_intl = [item.model_dump() for item in found_intl]
            except Exception as exc_intl:
                logger.warning("Uluslararası emsal arama atlandı: %s", exc_intl)
                raw_intl = []

        international_rulings: List[InternationalRuling] = []
        for item in raw_intl:
            try:
                international_rulings.append(InternationalRuling(**item))
            except Exception:
                pass

        has_intl = len(international_rulings) > 0
        if has_intl:
            consulted = list(dict.fromkeys(consulted + ["US_CBP_CROSS", "CN_GACC"]))

        # Uluslararası emsal bulunamadıysa kullanıcıya uydurma karar değil, resmi
        # portallarda elle araması için doğrudan arama bağlantıları sunulur.
        research_portal_links: Optional[Dict[str, str]] = None
        if not has_intl:
            try:
                from api.modules.international_search import generate_portal_links
                research_portal_links = generate_portal_links(
                    raw_text, locked_digits[:6] if locked_digits else None
                )
            except Exception as exc_links:
                logger.warning("Portal bağlantıları üretilemedi: %s", exc_links)

        intl_legal_sources = [
            LegalSource(
                source_type=f"INTL_{ir.country}",
                reference_no=ir.ruling_no,
                title=f"{ir.source_name} {ir.ruling_no} ({ir.country})",
                publication_date=ir.issue_date or None,
                excerpt=ir.product_description[:300],
                source_url=ir.source_url,
                legal_role="INDIVIDUAL_PRECEDENT",
                authority_level=4,
                is_binding=False,
            )
            for ir in international_rulings
        ] if has_intl else []

        # Resmi Kanuni Maddeler (Model yazmaz; sistem doğrudan veritabanından çeker)
        applied_gir_keys = list(traversal.get("applied_gir_keys") or [])
        cited_chapters = list(traversal.get("cited_chapter_notes") or [])

        from api.db.tgtc_knowledge_base import get_official_statute_records, OFFICIAL_GIR_FULL_STATUTES
        official_statutes = get_official_statute_records(
            gtip_code=formatted_code,
            applied_gir_keys=applied_gir_keys,
            cited_chapters=cited_chapters,
        )

        effective_gir_keys = list(applied_gir_keys) if applied_gir_keys else ["GIR_1", "GIR_6"]
        for fallback_k in ("GIR_1", "GIR_6"):
            if fallback_k not in effective_gir_keys:
                effective_gir_keys.append(fallback_k)

        applied_gir_rule_texts = []
        for k in effective_gir_keys:
            clean_k = str(k).upper().replace("GYK", "GIR").replace("(", "").replace(")", "").replace(" ", "_").strip()
            statute = OFFICIAL_GIR_FULL_STATUTES.get(clean_k)
            if statute:
                applied_gir_rule_texts.append(f"{statute['rule_no']}: {statute['text']}")

        all_legal_sources = official_statutes + [
            s for s in candidate.legal_sources
            if s.source_type not in {"TGTC_2026", "GIR", "TGTC_HEADING", "TGTC_SUBHEADING", "TGTC_LEAF", "FASIL_NOTU"}
        ] + ebti_legal_sources + intl_legal_sources
        dedup_legal_sources = []
        seen_source_keys = set()
        for src in all_legal_sources:
            s_key = (src.source_type, src.reference_no)
            if s_key not in seen_source_keys:
                seen_source_keys.add(s_key)
                dedup_legal_sources.append(src)

        confidence = compute_confidence(traversal, precedents, ebti_precedents)
        below_threshold = confidence < settings.CONFIDENCE_THRESHOLD

        decision = GTIPDecision(
            session_id=session_id,
            status="COMPLETED",
            gtip_code=formatted_code,
            confidence_score=confidence,
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
            applied_gir_rules=applied_gir_rule_texts,
            precedent_btbs=precedents,
            precedent_ebtis=ebti_precedents,
            international_rulings=international_rulings,
            research_portal_links=research_portal_links,
            legal_sources=dedup_legal_sources,
            consulted_sources=consulted,
            trade_measures=get_customs_trade_measures(formatted_code),
            state_machine_stage="MODEL_CLOSED_SET_COMPLETED",
            guardrail_status="VERIFIED_LEAF",
            # Statü COMPLETED kalır: arayüz statüyü tam eşitlikle render ettiği
            # için yeni bir statü boş ekran üretirdi. Eşik altı kararlar şemada
            # zaten tanımlı MANUAL_REVIEW değeriyle işaretlenir; GTIPResultCard
            # düşük skoru kendi güven bantlarıyla zaten uyarı olarak gösterir.
            legal_validation_status="MANUAL_REVIEW" if below_threshold else "PASSED",
            audit_notes=[
                (
                    "Kod, tam eşleşen gerçek BTB emsalinden alındı; model GTİP kodu üretmedi."
                    if is_exact_btb
                    else "Model serbest GTİP kodu üretmedi; yalnız sunulan seçenek kimliğini seçti."
                ),
                "Kod, ebeveyn yolu, 12 haneli yaprak ve yürürlük durumu sunucuda doğrulandı.",
                *(
                    [f"BROKER_APPROVAL_REQUIRED: Güven skoru {confidence:.2f} < eşik "
                     f"{settings.CONFIDENCE_THRESHOLD:.2f}; kıdemli müşavir onayı gerekir."]
                    if below_threshold else []
                ),
                *(
                    ["RESIDUAL_FALLBACK: Model hiçbir özel dalı eşleştiremedi; "
                     "resmî kalıntı ('diğerleri') dalı seçildi."]
                    if traversal.get("used_residual_fallback") else []
                ),
                *(
                    [f"AB EBTI emsali bulundu: {len(ebti_precedents)} karar (CN-8 uyumu ile)."]
                    if has_ebti else []
                ),
                *(
                    [f"Uluslararası emsal bulundu: {len(international_rulings)} karar (ABD CBP / Çin GACC / AB EBTI)."]
                    if has_intl else []
                ),
            ],
        )
        _record_run(session_id, raw_text, features, traversal, decision)
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
        raw_text: str = "",
        precedents: Optional[List[Any]] = None,
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
            raw_text=raw_text,
            precedents=precedents,
        )

    def start_analysis(
        self,
        raw_text: str,
        image_uri: str = None,
        enable_international_research: bool = False,
        exclude_btb_refs: Optional[Set[str]] = None,
    ) -> GTIPDecision:
        """`exclude_btb_refs` yalnız benchmark içindir; üretim yolunda None'dır."""
        session_id = str(uuid.uuid4())
        started = time.perf_counter()
        features = feature_extractor.extract_features(raw_text, image_uri)
        btb_precedents = rag_engine.search_btb_precedents(
            raw_text, exclude_refs=exclude_btb_refs
        )
        # EBTI araması: BTB aramasından bağımsız çalışır, hata durumunda boş liste döner
        try:
            ebti_precedents = rag_engine.search_ebti_precedents(raw_text)
        except Exception as exc_ebti:
            logger.warning("EBTI emsal araması atlandı: %s", exc_ebti)
            ebti_precedents = []

        # Uluslararası emsal araması (enable_international_research aktifse önceden çalıştır)
        international_rulings = []
        if enable_international_research:
            try:
                from api.modules.international_search import search_international_rulings
                found_intl = search_international_rulings(product_text=raw_text)
                international_rulings = [item.model_dump() for item in found_intl]
            except Exception as exc_intl:
                logger.warning("Uluslararası emsal ön taraması atlandı: %s", exc_intl)
                international_rulings = []

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
                    "international_rulings": international_rulings,
                    "enable_international_research": enable_international_research,
                },
            )
        else:
            # BTB ve EBTI emsalleri artık yalnız ekranda gösterilmiyor; seçim
            # yapan modele delil olarak veriliyor.
            tree_result = self._search(
                session_id,
                features,
                raw_text=raw_text,
                precedents=[*btb_precedents, *ebti_precedents],
            )
            tree_result.traversal_state["btb_precedents"] = [
                item.model_dump() for item in btb_precedents
            ]
            tree_result.traversal_state["ebti_precedents"] = [
                item.model_dump() for item in ebti_precedents
            ]
            tree_result.traversal_state["international_rulings"] = international_rulings
            tree_result.traversal_state["enable_international_research"] = enable_international_research
        duration_ms = (time.perf_counter() - started) * 1000
        if tree_result.discriminator_question:
            decision = self._pause(session_id, raw_text, image_uri, features, tree_result)
        else:
            decision = self._complete(session_id, raw_text, image_uri, features, tree_result)

        # Yapılandırılmış alanlar: log-based metric'ler metin ayrıştırmadan
        # doğrudan jsonPayload üzerinden türetilebilir (api/logging_config.py).
        logger.info(
            "[PipelineTiming] stage=model_closed_set status=%s duration_ms=%.2f",
            decision.status,
            duration_ms,
            extra={
                "session_id": session_id,
                "stage": "model_closed_set",
                "decision_status": decision.status,
                "duration_ms": round(duration_ms, 2),
                "btb_hits": len(btb_precedents),
                "ebti_hits": len(ebti_precedents),
                "intl_hits": len(international_rulings),
                "gtip_code": decision.gtip_code,
                "confidence_score": decision.confidence_score,
            },
        )
        return decision


    async def start_analysis_async(
        self,
        raw_text: str,
        image_uri: str = None,
        enable_international_research: bool = False,
    ) -> GTIPDecision:
        return await asyncio.to_thread(self.start_analysis, raw_text, image_uri, enable_international_research)

    async def start_analysis_stream(
        self,
        raw_text: str,
        image_uri: str = None,
        enable_international_research: bool = False,
    ) -> AsyncIterator[Dict[str, Any]]:
        yield {
            "stage": "MODEL_TARIFF_SELECTION",
            "status": "IN_PROGRESS",
            "message": "Gemini resmi TGTC ağacında fasıl, pozisyon ve alt pozisyon seçiyor.",
        }
        decision = await self.start_analysis_async(raw_text, image_uri, enable_international_research)
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
            # Bu vaka geri bildirim için değerlidir: müşavir ayrımı bilmiyorsa
            # soru ya yanlış sorulmuştur ya da kullanıcıca gözlenebilir değildir.
            decision = self._manual_review(
                session_id,
                "Kullanıcı gerekli teknik ayrımı bilmiyor olarak işaretledi.",
                "USER_INFORMATION_MISSING",
                raw_text=state.get("raw_text", ""),
                features=ProductFeatures(**state.get("product_features", {}))
                if state.get("product_features") else None,
                traversal=dict(state.get("discriminator_traversal") or {}),
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
            raw_text=state.get("raw_text", ""),
            precedents=_restore_precedents(traversal),
            locked_chapter=locked_chapter,
            locked_heading=locked_heading,
            locked_subheading=locked_subheading,
            locked_gtip=locked_gtip,
            query_vector=traversal.get("query_vector"),
        )
        # Yalnız btb_precedents'i geri yüklemek, HITL'den geçen kararların
        # doğrudan tamamlananlardan farklı hukuki dayanakla sonuçlanmasına yol
        # açıyordu; ayrıca uluslararası arama her devamda yeniden tetikleniyordu.
        for carried_key in (
            "btb_precedents",
            "ebti_precedents",
            "international_rulings",
            "enable_international_research",
            "applied_gir_keys",
            "cited_chapter_notes",
            "used_residual_fallback",
        ):
            if carried_key in traversal:
                tree_result.traversal_state.setdefault(carried_key, traversal[carried_key])

        # Müşavir kaç teknik ayrımı yanıtladı: güven skoruna girer.
        tree_result.traversal_state["hitl_answer_count"] = (
            int(traversal.get("hitl_answer_count") or 0) + 1
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
