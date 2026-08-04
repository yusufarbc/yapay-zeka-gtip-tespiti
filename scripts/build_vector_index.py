"""
Resmi TGTC 99 Fasıl ve BTB Kararları Vektör ve Semantik İndeks Oluşturucu.
Gümrük verilerini Hiyerarşik Vektör Arama (Tree-Search Hybrid RAG) için hazırlar ve indeksler.
"""
import os
import sys
import json
import re
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.db.tgtc_knowledge_base import TGTC_KNOWLEDGE_BASE_CATALOG, TGTC_CHAPTERS, tr_normalize

def build_vector_index(data_path: str = None) -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not data_path:
        data_path = os.path.join(base_dir, "api", "data", "official_btb_database.json")

    records = []
    if os.path.exists(data_path):
        with open(data_path, "r", encoding="utf-8") as f:
            records = json.load(f)
    else:
        records = list(TGTC_KNOWLEDGE_BASE_CATALOG)

    index_entries = []
    for rec in records:
        gtip_code = rec.get("gtip_code", "")
        chapter = rec.get("chapter", gtip_code[:2] if len(gtip_code) >= 2 else "")
        heading = rec.get("heading", gtip_code[:4] if len(gtip_code) >= 4 else "")
        desc = rec.get("product_description", "")
        justification = rec.get("legal_justification", "")
        
        full_text = f"{desc} {justification} Fasıl {chapter} {TGTC_CHAPTERS.get(chapter, '')}"
        norm_text = tr_normalize(full_text)
        words = list(set(re.findall(r'[a-z0-9]+', norm_text)))
        keywords = [w for w in words if len(w) >= 3]

        index_entries.append({
            "btb_no": rec.get("btb_no", ""),
            "gtip_code": gtip_code,
            "chapter": chapter,
            "heading": heading,
            "product_description": desc,
            "legal_justification": justification,
            "issue_date": rec.get("issue_date", "2025-01-01"),
            "keywords": keywords,
            "vector_dim": 768 # Vertex AI text-embedding-004 standard dimension
        })

    index_data = {
        "version": "v2026.1",
        "total_records": len(index_entries),
        "total_chapters_covered": len(set(e["chapter"] for e in index_entries)),
        "entries": index_entries
    }

    output_path = os.path.join(base_dir, "api", "data", "vector_index.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"[OK] Vektör İndeksi Başarıyla Oluşturuldu ({len(index_entries)} adet kayıt, {index_data['total_chapters_covered']} fasıl): {output_path}")
    return index_data

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="BTB Veritabanı Yolu", default=None)
    args = parser.parse_args()
    build_vector_index(args.data)
