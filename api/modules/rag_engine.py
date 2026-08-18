from typing import List
from api.schemas.product import ProductFeatures, GTIPCandidate, PrecedentBTB
from api.db.gcp_emulator import local_vector_store
from api.db.tgtc_knowledge_base import TGTC_CHAPTERS
from api.config import settings

class RAGEngine:
    """
    Modül 3: BTB Ağırlıklı Hybrid RAG Engine.
    Hiyerarşik Tree-Search: Kural motorunun izin verdiği Fasıllar (allowed_chapters) altında 
    ve genel vektör uzayında çift yönlü semantik tarama yapar. 
    Herhangi bir ürün için dinamik GTİP ve mevzuat gerekçesi türetir.
    """

    def search_candidates(
        self, 
        features: ProductFeatures, 
        allowed_chapters: List[str],
        applied_gir_rules: List[str] = None
    ) -> List[GTIPCandidate]:
        query_text = f"{features.product_name} {features.primary_material} {features.intended_use}"
        is_hard_locked = any("[HARD LOCK]" in r for r in (applied_gir_rules or []))
        
        # 1. Kısıtlı Fasıl Araması (Tree-Search)
        constrained_results = []
        if allowed_chapters:
            constrained_results = local_vector_store.search_btb(
                query_text=query_text,
                allowed_chapters=allowed_chapters,
                top_k=5
            )

        # 2. Top-K Aday Eşleştirme (Katı Fasıl Kilit Varsa Asla Global Fallback Yapılamaz)
        if constrained_results:
            constrained_results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            top_results = constrained_results[:3]
        elif is_hard_locked:
            # Sıfır Halüsinasyon Prensibi: Katı kural fasıl zırhı dışından emsal uydurulmaz
            top_results = []
        else:
            global_results = local_vector_store.search_btb(
                query_text=query_text,
                allowed_chapters=None,
                top_k=3
            )
            global_results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            top_results = global_results[:3]

        candidates = []
        if top_results:
            from api.db.tgtc_knowledge_base import load_tgtc_rules_and_notes
            rules_db = load_tgtc_rules_and_notes()
            chapter_notes = rules_db.get("fasil_notlari", {})

            for res in top_results:
                btb_sim = res.get("similarity_score", 0.85)
                res_chap = str(res.get("chapter", res.get("gtip_code", "")[:2])).zfill(2)
                
                base_legal = res.get("legal_justification", "TGTC 2026 Mevzuatı")
                chap_note = chapter_notes.get(res_chap, "")
                if chap_note and "[2026 Fasıl" not in base_legal:
                    base_legal += f" [2026 Fasıl {res_chap} Resmi Hukuki İzahname & GİR Uyumu: {chap_note}]"

                precedent = PrecedentBTB(
                    btb_no=res.get("btb_no", f"EMSAL-{res['gtip_code'][:4]}"),
                    gtip_code=res["gtip_code"],
                    issue_date=res.get("issue_date", "2026-01-01"),
                    product_description=res["product_description"],
                    legal_justification=base_legal,
                    similarity_score=btb_sim
                )

                # Bilimsel Ağırlıklı Ortak RAG Skoru (BTB Benzerliği * 0.70 + TGTC Fasıl Uyumu * 0.30)
                res_chap = res.get("chapter", res.get("gtip_code", "")[:2])
                tgtc_chap_score = 1.0 if (allowed_chapters and res_chap in allowed_chapters) else 0.60
                combined_score = (btb_sim * settings.BTB_WEIGHT) + (tgtc_chap_score * settings.TGTC_WEIGHT)

                candidate = GTIPCandidate(
                    gtip_code=res["gtip_code"],
                    description=res["product_description"],
                    chapter=res["chapter"],
                    heading=res["heading"],
                    score=round(min(0.98, max(0.50, combined_score)), 3),
                    precedents=[precedent]
                )
                candidates.append(candidate)

        return candidates

rag_engine = RAGEngine()
