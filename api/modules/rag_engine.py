from typing import List
from api.schemas.product import ProductFeatures, GTIPCandidate, PrecedentBTB
from api.db.gcp_emulator import local_vector_store
from api.config import settings

class RAGEngine:
    """
    Modül 3: BTB Ağırlıklı Hybrid RAG Engine.
    Hiyerarşik Tree-Search: Kural motorunun izin verdiği Fasıllar (allowed_chapters) altında 
    ve genel vektör uzayında çift yönlü semantik tarama yapar.
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

        # Sonuçları birleştir ve en yüksek benzerlik puanına göre sırala
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
        for res in top_results:
            precedent = PrecedentBTB(
                btb_no=res.get("btb_no", f"EMSAL-{res['gtip_code'][:4]}"),
                gtip_code=res["gtip_code"],
                issue_date=res.get("issue_date", "2025-01-01"),
                product_description=res["product_description"],
                legal_justification=res["legal_justification"],
                similarity_score=res["similarity_score"]
            )

            # RAG Skoru (BTB ağırlıklı)
            combined_score = (res["similarity_score"] * settings.BTB_WEIGHT) + 0.25

            candidate = GTIPCandidate(
                gtip_code=res["gtip_code"],
                description=res["product_description"],
                chapter=res["chapter"],
                heading=res["heading"],
                score=round(combined_score, 3),
                precedents=[precedent]
            )
            candidates.append(candidate)

        return candidates

rag_engine = RAGEngine()
