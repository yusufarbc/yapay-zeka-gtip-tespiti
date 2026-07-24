from typing import List
from api.schemas.product import ProductFeatures, GTIPCandidate, PrecedentBTB
from api.db.gcp_emulator import local_vector_store
from api.config import settings

class RAGEngine:
    """
    Modül 3: BTB Ağırlıklı Hybrid RAG Engine.
    Kural motorunun izin verdiği Fasıllar (allowed_chapters) altında 
    emsal BTB kararlarını (%70 ağırlık) ve TGTC izahnamelerini (%30 ağırlık) taranır.
    """

    def search_candidates(
        self, 
        features: ProductFeatures, 
        allowed_chapters: List[str]
    ) -> List[GTIPCandidate]:
        query_text = f"{features.product_name} {features.primary_material} {features.intended_use}"
        
        # Local Vector Store'dan taranır (Vertex AI Vector Search emülatörü)
        raw_results = local_vector_store.search_btb(
            query_text=query_text,
            allowed_chapters=allowed_chapters,
            top_k=3
        )

        candidates = []
        for res in raw_results:
            precedent = PrecedentBTB(
                btb_no=res["btb_no"],
                gtip_code=res["gtip_code"],
                issue_date=res["issue_date"],
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
