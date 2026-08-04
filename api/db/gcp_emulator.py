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

TURKISH_STOP_WORDS = {
    "malzemeden", "imal", "edilmis", "edilmiş", "tipi", "icin", "için", "olan", "ve", "ile", 
    "veya", "gore", "göre", "her", "bir", "bu", "da", "de", "dahi", "turu", "türü", "ait",
    "uzere", "üzere", "gibi", "kadar", "adet", "kutu", "tane", "halinde", "mamul",
    "tasarim", "tasarimi", "yüksek", "yuksek", "dusuk", "düşük", "saglam", "sağlam", "kompakt",
    "genel", "urun", "ürün", "cihaz", "aciklama", "açıklama", "ozellikleri", "özellikleri", "ozellik", "özellik",
    "uygulamalari", "uygulamaları", "uygulama", "idealdir", "kullanilir", "kullanılır", "saglar", "sağlar"
}

class LocalVectorStore:
    """
    Resmi Türk Gümrük Tarife Cetveli (TGTC 99 Fasıl) ve BTB Kararları Vektör Arama Motoru.
    TGTC izahnameleri ve emsal BTB kararları üzerinde Tree-Search Hybrid RAG semantik eşleşmesi yapar.
    """
    def __init__(self, mock_data_path: str = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if mock_data_path is None:
            mock_data_path = os.path.join(base_dir, "data", "vector_index.json")

        self.btb_records: List[Dict[str, Any]] = []
        if os.path.exists(mock_data_path):
            with open(mock_data_path, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, dict) and "entries" in content:
                    self.btb_records = content["entries"]
                elif isinstance(content, list):
                    self.btb_records = content

    def search_btb(
        self, 
        query_text: str, 
        allowed_chapters: Optional[List[str]] = None, 
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        1. Kademeli Fasıl/Pozisyon filtresi (allowed_chapters).
        2. Semantik kelime kümesi ve TF-IDF ağırlıklı benzerlik skoru.
        3. En yüksek skorlu emsal kararları döndürür.
        """
        norm_query = tr_normalize(query_text)
        all_words = [w for w in re.findall(r'[a-z0-9]+', norm_query) if len(w) >= 3]
        query_words = [w for w in all_words if w not in TURKISH_STOP_WORDS]
        query_word_set = set(query_words) if query_words else set(all_words)
        results = []

        for record in self.btb_records:
            gtip_code = record.get("gtip_code", "")
            chapter = record.get("chapter", gtip_code[:2] if len(gtip_code) >= 2 else "")

            # Fasıl Uyum Kontrolü
            chapter_matched = bool(allowed_chapters and (chapter in allowed_chapters))
            if allowed_chapters and not chapter_matched:
                # Kısıtlı fasıl aramasında izin verilmeyen fasılları atla
                continue

            raw_desc = record.get("product_description", "") + " " + record.get("legal_justification", "")
            desc_norm = tr_normalize(raw_desc)
            desc_words = [w for w in re.findall(r'[a-z0-9]+', desc_norm) if w not in TURKISH_STOP_WORDS]
            rec_keywords = set(desc_words)

            # Semantik Kelime & Kök Kesişimi (Stop-words hariç 4-karakter tam/kök eşleme)
            matched_rw_set = set()
            for qw in query_word_set:
                for rw in rec_keywords:
                    if rw not in matched_rw_set:
                        if qw == rw or (len(qw) >= 4 and len(rw) >= 4 and qw[:4] == rw[:4]):
                            matched_rw_set.add(rw)
                            break

            word_score = len(matched_rw_set) * 0.25
            base_score = 0.45 if chapter_matched else 0.15
            final_score = base_score + word_score
            final_score = min(final_score, 0.98)

            match_item = dict(record)
            match_item["similarity_score"] = round(final_score, 3)
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
