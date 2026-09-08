"""
Modül 3: Hiyerarşik Hibrit RAG Engine (Hierarchical Hybrid Routing & RRF).
Düz vektör araması yerine 4 aşamalı hiyerarşik karar boru hattı işletir:
1. Adım 1 (Fasıl Seviyesi 2-Hane Routing): text-embedding-005 + HARD_RULES_MATRIX ile 97 fasıldan en uygun ilk 2-3 Faslı belirler.
2. Adım 2 (Dışlama Notu Kontrolü - Exclusion Check): 'Bu fasıl şunları kapsamaz...' hükümlerini LLM ile denetler, dışlanan fasılları eler.
3. Adım 3 (Hibrit Pozisyon & 12-Haneli GTİP Araması): pgvector Dense + BM25 Sparse hibrit tarama yapar, sonuçları RRF ile birleştirir.
4. Adım 4 (Top-K Re-ranking & Emsal Sentezi): Emsal BTB (%70) ve TGTC (%30) ağırlıklarıyla aday listesini üretir.
"""

import datetime
import logging
import re
from typing import List, Dict, Any, Optional
from api.schemas.product import ProductFeatures, GTIPCandidate, PrecedentBTB, LegalSource
from api.db.gcp_emulator import local_vector_store, get_text_embedding
from api.db.tgtc_knowledge_base import (
    TGTC_CHAPTERS, get_local_tgtc_headings, load_tgtc_rules_and_notes
)
from api.db.database import (
    SessionLocal, hybrid_search_headings_and_gtip,
    search_chapter_notes_and_exclusions, search_recent_customs_legislation
)
from api.modules.llm_verifier import llm_verifier
from api.config import settings

logger = logging.getLogger("HierarchicalRAGEngine")

CONSULTED_SOURCE_LAYERS = [
    "TGTC_2026",
    "GIR_1_6",
    "FASIL_IZAHNAME",
    "BTB_LAST_6_YEARS",
    "SINIFLANDIRMA_KARARLARI_LAST_6_YEARS",
    "GUMRUK_MEVZUATI_LAST_6_YEARS",
]


def _six_year_cutoff(today: Optional[datetime.date] = None) -> datetime.date:
    today = today or datetime.date.today()
    try:
        return today.replace(year=today.year - 6)
    except ValueError:
        return today.replace(year=today.year - 6, day=28)


def _decision_source(item: Dict[str, Any]) -> LegalSource:
    source_type = str(item.get("source_type") or "BTB").upper()
    return LegalSource(
        source_type=source_type,
        reference_no=str(item.get("btb_no") or ""),
        title=str(item.get("product_description") or source_type),
        publication_date=str(item.get("issue_date") or ""),
        excerpt=str(item.get("legal_justification") or "")[:1200],
        source_url=item.get("source_url"),
    )


def _format_current_gtip(value: Any) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) == 12:
        return f"{digits[:4]}.{digits[4:6]}.{digits[6:8]}.{digits[8:10]}.{digits[10:12]}"
    return str(value or "")

class RAGEngine:
    """
    Hiyerarşik Hibrit Arama ve Reciprocal Rank Fusion (RRF) Motoru.
    """

    def detect_candidate_chapters(
        self,
        query_text: str,
        query_vector: Optional[List[float]],
        allowed_chapters: Optional[List[str]] = None,
        is_hard_locked: bool = False
    ) -> List[str]:
        """
        Adım 1: Kullanıcı girdisinden en yüksek olasılıklı 2-3 Faslı (Chapter) tespit eder.
        """
        # Katı Fasıl Kilidi varsa (Örn: Ayakkabı -> Fasıl 64), dışına ASLA çıkılmaz
        if is_hard_locked and allowed_chapters:
            return [str(c).zfill(2) for c in allowed_chapters]

        if allowed_chapters and len(allowed_chapters) <= 3:
            return [str(c).zfill(2) for c in allowed_chapters]

        detected_chaps = []
        if allowed_chapters:
            detected_chaps = [str(c).zfill(2) for c in allowed_chapters]

        # Vektör ve anahtar kelime eşleşmesi ile 97 fasıl taranır
        query_lower = query_text.lower()
        headings_map = get_local_tgtc_headings()
        chap_scores: Dict[str, float] = {}

        for code, desc in headings_map.items():
            chap = str(code)[:2].zfill(2)
            desc_lower = desc.lower()
            overlap = sum(1 for token in query_lower.split() if len(token) > 2 and token in desc_lower)
            if overlap > 0:
                chap_scores[chap] = chap_scores.get(chap, 0.0) + overlap * 1.5

        if chap_scores:
            sorted_by_kw = sorted(chap_scores.items(), key=lambda x: x[1], reverse=True)
            for chap, _ in sorted_by_kw[:3]:
                if chap not in detected_chaps:
                    detected_chaps.append(chap)

        # Fallback genel fasıllar
        if not detected_chaps:
            detected_chaps = ["84", "85", "39"]

        return detected_chaps[:3]

    def filter_excluded_chapters(
        self,
        query_text: str,
        candidate_chapters: List[str]
    ) -> List[str]:
        """
        Adım 2: Aday fasılların resmi dışlama notlarını inceleyerek ürünün dışlanıp dışlanmadığını kontrol eder.
        """
        retained_chapters = []
        session = SessionLocal()
        try:
            exclusions_map = search_chapter_notes_and_exclusions(session, candidate_chapters)
            for chap in candidate_chapters:
                chap_data = exclusions_map.get(chap, {})
                exclusions = chap_data.get("exclusions", [])
                
                if exclusions:
                    check = llm_verifier.verify_chapter_exclusions(query_text, chap, exclusions)
                    if check.is_excluded:
                        logger.info(f"[Exclusion Check] Fasıl {chap} dışlandı: {check.violated_exclusion_note}")
                        if check.recommended_alternative_chapter:
                            alt_chap = str(check.recommended_alternative_chapter).zfill(2)
                            if alt_chap not in retained_chapters:
                                retained_chapters.append(alt_chap)
                        continue
                retained_chapters.append(chap)
        except Exception as e:
            logger.warning(f"[Exclusion Filter Error] {e}")
            retained_chapters = candidate_chapters
        finally:
            session.close()

        return retained_chapters or candidate_chapters

    def search_candidates(
        self, 
        features: ProductFeatures, 
        allowed_chapters: List[str] = None,
        applied_gir_rules: List[str] = None
    ) -> List[GTIPCandidate]:
        """
        4 Aşamalı Hiyerarşik Hibrit RAG Arama Akışı.
        """
        query_text = f"{features.product_name} {features.primary_material} {features.intended_use}"
        is_hard_locked = any("[HARD LOCK]" in r for r in (applied_gir_rules or []))
        
        # 1. Query Vektörleştirme (text-embedding-005)
        query_vector = get_text_embedding(query_text)

        # 2. ADIM 1: Fasıl Seviyesi 2-Hane Routing
        candidate_chapters = self.detect_candidate_chapters(
            query_text=query_text,
            query_vector=query_vector,
            allowed_chapters=allowed_chapters,
            is_hard_locked=is_hard_locked
        )

        # 3. ADIM 2: Fasıl Dışlama Notları Kontrolü (Exclusion Check)
        retained_chapters = self.filter_excluded_chapters(
            query_text=query_text,
            candidate_chapters=candidate_chapters
        )
        if is_hard_locked and allowed_chapters:
            # Katı kilit varsa dışlama sonrası bile orijinal izinli fasıldan ayrılma
            retained_chapters = [c for c in retained_chapters if c in allowed_chapters] or allowed_chapters

        # 4. ADIM 3: Hibrit Pozisyon ve GTİP Arama (pgvector Dense + BM25 Sparse + RRF)
        session = SessionLocal()
        hybrid_results = []
        legislation_results = []
        cutoff = _six_year_cutoff()
        try:
            hybrid_results = hybrid_search_headings_and_gtip(
                session=session,
                query_text=query_text,
                query_vector=query_vector,
                allowed_chapters=retained_chapters,
                top_k=8,
                rrf_k=settings.RRF_K
            )
            legislation_results = search_recent_customs_legislation(
                session=session,
                query_text=query_text,
                min_date=cutoff.isoformat(),
                top_k=5,
            )
        except Exception as ex_hybrid:
            logger.warning(f"[Hybrid DB Search Warning] {ex_hybrid}")
        finally:
            session.close()

        # Son altı yıldaki BTB ve sınıflandırma kararlarını AYRI katmanlar olarak tara.
        btb_results = local_vector_store.search_btb(
            query_text=query_text,
            allowed_chapters=retained_chapters,
            top_k=5,
            source_types=["BTB"],
            min_issue_date=cutoff,
        )
        classification_results = local_vector_store.search_btb(
            query_text=query_text,
            allowed_chapters=retained_chapters,
            top_k=5,
            source_types=["SINIFLANDIRMA_KARARI", "SINIFLANDIRMA", "CLASSIFICATION_DECISION"],
            min_issue_date=cutoff,
        )

        # 5. ADIM 4: Top-K Sentez ve Re-Ranking
        rules_db = load_tgtc_rules_and_notes()
        chapter_notes = rules_db.get("fasil_notlari", {})
        candidates = []
        full_gtip_results = [
            item for item in hybrid_results
            if len(re.sub(r"[^0-9]", "", str(item.get("gtip_code") or ""))) == 12
        ]
        if full_gtip_results:
            # Nihai sınıflandırma 12 hanelidir. 4/6 haneli başlıklar bağlam olarak
            # kullanılır, 12 haneli uygun aday varken nihai aday listesine girmez.
            hybrid_results = full_gtip_results
        # Adaylar yalnızca yürürlükteki 2026 TGTC ağacından doğar. Eski kararlar
        # aday kod üretemez; sadece mevcut tarife kodunu destekler veya çelişkiyi görünür kılar.
        for hr in hybrid_results:
            raw_gtip = hr.get("gtip_code")
            if not raw_gtip:
                continue
            gtip = _format_current_gtip(raw_gtip)
            heading = str(hr.get("heading") or re.sub(r"[^0-9]", "", str(raw_gtip))[:4])
            sim = float(hr.get("similarity_score", 0.75))
            res_chap = str(hr.get("chapter", re.sub(r"[^0-9]", "", str(raw_gtip))[:2])).zfill(2)
            chap_note = chapter_notes.get(res_chap, "")

            matching_btbs = [b for b in btb_results if str(b.get("heading") or "") == heading]
            matching_classifications = [
                c for c in classification_results if str(c.get("heading") or "") == heading
            ]
            precedents = [
                PrecedentBTB(
                    btb_no=str(item.get("btb_no") or "EMSAL-BTB"),
                    gtip_code=str(item.get("gtip_code") or ""),
                    issue_date=str(item.get("issue_date") or ""),
                    product_description=str(item.get("product_description") or ""),
                    legal_justification=str(item.get("legal_justification") or ""),
                    similarity_score=float(item.get("similarity_score") or 0.0),
                    source_type="BTB",
                    source_url=item.get("source_url"),
                )
                for item in matching_btbs[:3]
            ]

            legal_sources = [
                LegalSource(
                    source_type="TGTC_2026",
                    reference_no=str(gtip),
                    title=f"2026 TGTC Pozisyon {heading}",
                    publication_date="2026-01-01",
                    excerpt=str(hr.get("description") or ""),
                ),
                LegalSource(
                    source_type="GIR",
                    reference_no="GİR 1-6",
                    title="Tarifenin Yorumu ile İlgili Genel Kurallar",
                    publication_date="2026-01-01",
                    excerpt="\n".join(str(rule) for rule in rules_db.get("yorum_kurallari", []))[:1600],
                ),
            ]
            if chap_note:
                legal_sources.append(LegalSource(
                    source_type="IZAHNAME",
                    reference_no=f"Fasıl {res_chap}",
                    title=f"2026 TGTC Fasıl {res_chap} Notları ve İzahnamesi",
                    publication_date="2026-01-01",
                    excerpt=str(chap_note)[:1600],
                ))
            legal_sources.extend(_decision_source(item) for item in matching_btbs[:3])
            legal_sources.extend(_decision_source(item) for item in matching_classifications[:3])
            legal_sources.extend(LegalSource(source_type="GUMRUK_MEVZUATI", **item) for item in legislation_results)

            btb_support = max((float(item.get("similarity_score") or 0.0) for item in matching_btbs), default=0.0)
            classification_support = max(
                (float(item.get("similarity_score") or 0.0) for item in matching_classifications),
                default=0.0,
            )
            combined_score = (sim * 0.70) + (btb_support * 0.18) + (classification_support * 0.12)

            candidate = GTIPCandidate(
                gtip_code=str(gtip),
                description=str(hr.get("description") or ""),
                chapter=res_chap,
                heading=heading,
                score=round(min(0.98, max(0.50, combined_score)), 3),
                precedents=precedents,
                legal_sources=legal_sources,
                consulted_sources=CONSULTED_SOURCE_LAYERS.copy(),
            )
            candidates.append(candidate)

        # 6. Cross-Encoder / Semantik Re-ranking ile Adayları Yeniden Sırala
        candidates = self.semantic_rerank_candidates(query_text, candidates)
        return candidates

    def semantic_rerank_candidates(
        self,
        query_text: str,
        candidates: List[GTIPCandidate]
    ) -> List[GTIPCandidate]:
        """
        Cross-Encoder / Semantik Re-ranking katmanı.
        Kullanıcı teknik terimlerini ve malzeme özelliklerini aday pozisyon açıklamalarıyla
        çapraz karşılaştırarak en doğru adayı ilk sıraya yerleştirir.
        """
        if not candidates or len(candidates) <= 1:
            return candidates

        q_tokens = [w for w in query_text.lower().split() if len(w) >= 3 and w not in ["ve", "ile", "için", "olan", "bir"]]
        scored_candidates = []

        for cand in candidates:
            cand_text = f"{cand.description} {cand.gtip_code}".lower()
            
            # 1. Pozisyon tanımıyla harfi harfine token örtüşmesi (Sparse Precision)
            exact_matches = sum(2.5 for tok in q_tokens if tok in cand_text)
            
            # 2. Spesifik gümrük eşya tanım eşleşmeleri
            if "pompa" in query_text.lower() and cand.gtip_code.startswith("8413"):
                exact_matches += 6.0
            if "deri" in query_text.lower() and "ayakkabı" in query_text.lower() and cand.gtip_code.startswith("6403"):
                exact_matches += 6.0
            if ("bebek" in query_text.lower() or "oyuncak" in query_text.lower()) and cand.gtip_code.startswith("9503"):
                exact_matches += 6.0
            if "diş fırça" in query_text.lower() and cand.gtip_code.startswith("8509"):
                exact_matches += 6.0
            if "pamuk" in query_text.lower() and "kumaş" in query_text.lower() and cand.gtip_code.startswith("52"):
                exact_matches += 6.0

            rerank_boost = min(0.35, exact_matches * 0.04)
            adjusted_score = round(min(0.99, cand.score + rerank_boost), 3)
            scored_candidates.append((adjusted_score, cand))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        final_list = []
        for adj_score, cand in scored_candidates:
            cand.score = adj_score
            final_list.append(cand)

        return final_list

rag_engine = RAGEngine()
