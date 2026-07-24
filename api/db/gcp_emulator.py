import json
import os
import math
from typing import List, Dict, Any, Optional

class LocalVectorStore:
    """
    Offline Vertex AI Vector Search Emülatörü.
    Local geliştirmede mock BTB kararları ve TGTC izahnameleri üzerinde 
    vektör arama ve metadata chapter filtreleme yapar.
    """
    def __init__(self, mock_data_path: str = None):
        if mock_data_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            mock_data_path = os.path.join(base_dir, "data", "mock_btb_data.json")
        
        self.mock_data_path = mock_data_path
        self.btb_records = self._load_data()

    def _load_data(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.mock_data_path):
            with open(self.mock_data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def search_btb(
        self, 
        query_text: str, 
        allowed_chapters: Optional[List[str]] = None, 
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Girdi metnini anahtar kelimeler ve allowed_chapters filtresi ile tarar.
        """
        query_words = set(query_text.lower().split())
        results = []

        for record in self.btb_records:
            gtip_code = record.get("gtip_code", "")
            chapter = record.get("chapter", gtip_code[:2] if gtip_code else "")

            # 1. Allowed chapters filtresi (Hard exclusion)
            if allowed_chapters and chapter not in allowed_chapters:
                continue

            # 2. Skorlama (Anahtar Kelime Benzerliği + Metin Eşleşmesi)
            desc_text = (record.get("product_description", "") + " " + record.get("legal_justification", "")).lower()
            matching_words = [w for w in query_words if len(w) > 2 and w in desc_text]
            score = 0.50 + (len(matching_words) * 0.15)
            score = min(score, 0.98) # Max score 0.98

            match_item = dict(record)
            match_item["similarity_score"] = round(score, 3)
            results.append(match_item)

        # Skora göre sırala
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:top_k]

class LocalStateStore:
    """
    Offline Cloud Firestore State Emülatörü.
    Oturum durumlarını ve HITL soru-cevap durumlarını yerelde saklar.
    """
    def __init__(self):
        self._states: Dict[str, Dict[str, Any]] = {}

    def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._states.get(session_id)

    def save_state(self, session_id: str, state: Dict[str, Any]):
        self._states[session_id] = state

local_vector_store = LocalVectorStore()
local_state_store = LocalStateStore()
