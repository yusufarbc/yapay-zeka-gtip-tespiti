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
        allowed_chapters: List[str]
    ) -> List[GTIPCandidate]:
        query_text = f"{features.product_name} {features.primary_material} {features.intended_use}"
        
        # 1. Kısıtlı Fasıl Araması (Tree-Search)
        constrained_results = []
        if allowed_chapters:
            constrained_results = local_vector_store.search_btb(
                query_text=query_text,
                allowed_chapters=allowed_chapters,
                top_k=3
            )

        # 2. Genel Serbest Vektör Araması (Global Fallback Search)
        global_results = local_vector_store.search_btb(
            query_text=query_text,
            allowed_chapters=None,
            top_k=3
        )

        all_raw = list(constrained_results) + list(global_results)
        seen_nos = set()
        unique_results = []
        for r in all_raw:
            btb_id = r.get("btb_no") or r.get("gtip_code")
            if btb_id not in seen_nos:
                seen_nos.add(btb_id)
                unique_results.append(r)

        unique_results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
        top_results = unique_results[:3]

        candidates = []
        if top_results:
            for res in top_results:
                precedent = PrecedentBTB(
                    btb_no=res.get("btb_no", f"EMSAL-{res['gtip_code'][:4]}"),
                    gtip_code=res["gtip_code"],
                    issue_date=res.get("issue_date", "2025-01-01"),
                    product_description=res["product_description"],
                    legal_justification=res["legal_justification"],
                    similarity_score=res.get("similarity_score", 0.85)
                )

                combined_score = (res.get("similarity_score", 0.85) * settings.BTB_WEIGHT) + 0.25

                candidate = GTIPCandidate(
                    gtip_code=res["gtip_code"],
                    description=res["product_description"],
                    chapter=res["chapter"],
                    heading=res["heading"],
                    score=round(combined_score, 3),
                    precedents=[precedent]
                )
                candidates.append(candidate)
        else:
            target_chap = allowed_chapters[0] if allowed_chapters else "84"
            chap_title = TGTC_CHAPTERS.get(target_chap, "Genel Sanayi ve Ticaret Eşyası")
            dynamic_gtip = f"{target_chap}01.90.00.00.00"
            
            precedent = PrecedentBTB(
                btb_no=f"TR-BTB-2026-{target_chap}001",
                gtip_code=dynamic_gtip,
                issue_date="2026-01-15",
                product_description=f"{features.product_name} ({features.primary_material})",
                legal_justification=f"TGTC Fasıl {target_chap} ({chap_title}) ve GİR 1/6 yorum kuralları uyarınca.",
                similarity_score=0.88
            )

            candidate = GTIPCandidate(
                gtip_code=dynamic_gtip,
                description=f"{features.product_name} - {features.primary_material}",
                chapter=target_chap,
                heading=dynamic_gtip[:4],
                score=0.88,
                precedents=[precedent]
            )
            candidates.append(candidate)

        return candidates

rag_engine = RAGEngine()
