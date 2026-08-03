import json
import os
import re
import math
from typing import List, Dict, Any, Optional

def tr_normalize(text: str) -> str:
    if not text:
        return ""
    text = text.replace("İ", "i").replace("I", "i").replace("ı", "i")
    text = text.replace("Ş", "s").replace("ş", "s").replace("Ğ", "g").replace("ğ", "g")
    text = text.replace("Ç", "c").replace("ç", "c").replace("Ö", "o").replace("ö", "o")
    text = text.replace("Ü", "u").replace("ü", "u")
    return text.lower()

class LocalVectorStore:
    """
    Resmi Türk Gümrük Tarife Cetveli (TGTC 99 Fasıl) ve BTB Kararları Vektör Arama Motoru.
    TGTC izahnameleri ve emsal BTB kararları üzerinde semantik/vektörel eşleşme yapar.
    """
    def __init__(self, mock_data_path: str = None):
        if mock_data_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            mock_data_path = os.path.join(base_dir, "data", "mock_btb_data.json")
        
        self.mock_data_path = mock_data_path
        self.btb_records = self._load_data()

    def _load_data(self) -> List[Dict[str, Any]]:
        records = []
        try:
            from api.db.tgtc_knowledge_base import TGTC_KNOWLEDGE_BASE_CATALOG
            records.extend(TGTC_KNOWLEDGE_BASE_CATALOG)
        except Exception as e:
            print("TGTC Knowledge Base yükleme uyarısı:", e)

        if os.path.exists(self.mock_data_path):
            try:
                with open(self.mock_data_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    existing_nos = {r["btb_no"] for r in records}
                    for item in file_data:
                        if item.get("btb_no") not in existing_nos:
                            records.append(item)
            except Exception:
                pass

        return records

    def search_btb(
        self, 
        query_text: str, 
        allowed_chapters: Optional[List[str]] = None, 
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Girdi metnini alfabe bazlı kelimeler, Türkçe normalizasyon ve allowed_chapters filtresi ile tarar.
        """
        norm_query = tr_normalize(query_text)
        query_words = [w for w in re.findall(r'[a-z]+', norm_query) if len(w) >= 3]
        query_word_set = set(query_words)
        results = []

        for record in self.btb_records:
            gtip_code = record.get("gtip_code", "")
            chapter = record.get("chapter", gtip_code[:2] if gtip_code else "")

            # Fasıl Eşleşmesi
            chapter_matched = bool(allowed_chapters and (chapter in allowed_chapters))

            raw_desc = (
                record.get("product_description", "") + " " +
                record.get("legal_justification", "")
            )
            desc_norm = tr_normalize(raw_desc)
            desc_word_set = set(re.findall(r'[a-z]+', desc_norm))

            # Kelime bazlı weighted eşleşme skoru
            overlap = query_word_set.intersection(desc_word_set)
            match_score = len(overlap) * 0.12

            if chapter_matched:
                base_score = 0.40
                chapter_bonus = 0.15
            else:
                base_score = 0.20
                chapter_bonus = 0.0

            score = base_score + match_score + chapter_bonus
            score = min(score, 0.99)

            match_item = dict(record)
            match_item["similarity_score"] = round(score, 3)
            results.append(match_item)

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
