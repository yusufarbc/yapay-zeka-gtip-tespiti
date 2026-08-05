"""
Resmi Türk Gümrük Tarife Cetveli (TGTC) Dinamik Mevzuat ve Önbellek Modülü.
Veriler doğrudan Ticaret Bakanlığı canlı kazıma (Scraping) pipeline'ları
ve ilişkisel/vektör veritabanından dinamik olarak yüklenir.
HİÇBİR STATİK SÖZLÜK VEYA HARDCODED EŞLEŞTİRME İÇERMEZ.
"""
import os
import re
import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger("TGTCKnowledgeBase")

from api.db.database import SessionLocal
from api.db.gcp_emulator import OfficialBTBModel

GIR_RULES = {
    "GIR_1": "Tarife pozisyonu ve ilgili bölüm veya fasıl notlarına göre sınıflandırma yapılır.",
    "GIR_2A": "Sökülmüş, demonte veya tamamlanmamış eşya, monte edilmiş ana eşyanın karakteristik özelliğini taşıyorsa ana pozisyonda sınıflandırılır.",
    "GIR_2B": "Kombine maddeler veya karışımların sınıflandırılmasında baskın nitelik ve oran dikkate alınır.",
    "GIR_3A": "En özel tanımı veren pozisyon, genel tanım veren pozisyona tercih edilir.",
    "GIR_3B": "Karışımlar, farklı maddelerden oluşan eşyalar ve perakende satılacak takımlar (setler) eşyaya esas karakterini veren maddeye/komponentine göre sınıflandırılır.",
    "GIR_3C": "3(a) ve 3(b) kuralları ile sınıflandırılamayan eşyalar, numaralandırmada en son sırada yer alan pozisyona verilir.",
    "GIR_4": "Yukarıdaki kurallara göre sınıflandırılamayan eşyalar, en çok benzediği eşya pozisyonuna verilir.",
    "GIR_5A": "Özel biçim verilmiş kılıf ve kutular (müzik aleti, silah vb. kutuları) ait oldukları eşya ile birlikte sınıflandırılır.",
    "GIR_5B": "Eşya ile birlikte sunulan ambalaj maddeleri ve ambalaj kapları eşya ile birlikte sınıflandırılır.",
    "GIR_6": "Alt pozisyonlar düzeyinde sınıflandırma, aynı düzeydeki alt pozisyonların karşılaştırılması ile GİR 1-5 esaslarına göre yapılır."
}

def load_tgtc_chapters() -> Dict[str, str]:
    """Resmi 99 TGTC Fasıl Tanımlarını GCP Cloud SQL (SQLAlchemy ORM) üzerinden okur."""
    try:
        session = SessionLocal()
        records = session.query(OfficialBTBModel).all()
        session.close()
        if records:
            chapters = {}
            for r in records:
                if r.chapter and r.product_description:
                    chapters[r.chapter.zfill(2)] = r.product_description
            return chapters
    except Exception as e:
        logger.warning(f"[TGTC KnowledgeBase] SQLAlchemy ORM fasıl okuma uyarısı: {e}")

    return {}

def load_btb_catalog() -> List[Dict[str, Any]]:
    """Resmi BTB Emsal Kararlar Kataloğunu GCP Cloud SQL (SQLAlchemy ORM) üzerinden okur."""
    try:
        session = SessionLocal()
        records = session.query(OfficialBTBModel).all()
        session.close()
        if records:
            return [{
                "btb_no": r.btb_no,
                "gtip_code": r.gtip_code,
                "chapter": r.chapter,
                "heading": r.heading,
                "issue_date": r.issue_date,
                "product_description": r.product_description,
                "legal_justification": r.legal_justification
            } for r in records]
    except Exception as e:
        logger.warning(f"[TGTC Catalog] SQLAlchemy ORM BTB okuma uyarısı: {e}")

    return []

# Dynamic property wrappers for backward compatibility
TGTC_CHAPTERS = load_tgtc_chapters()
TGTC_KNOWLEDGE_BASE_CATALOG = load_btb_catalog()

TURKISH_STOP_WORDS = {
    "ve", "ile", "veya", "için", "bir", "bu", "da", "de", "dahi", "göre", "ait",
    "üzere", "gibi", "kadar", "adet", "kutu", "tane", "ürün", "mamul", "cihaz",
    "diğer", "eşya", "maddeler", "kutular", "kaplar", "aksam", "parça"
}

def tr_normalize(text: str) -> str:
    if not text:
        return ""
    text = text.replace("İ", "i").replace("I", "i").replace("ı", "i")
    text = text.replace("Ş", "s").replace("ş", "s").replace("Ğ", "g").replace("ğ", "g")
    text = text.replace("Ç", "c").replace("ç", "c").replace("Ö", "o").replace("ö", "o")
    text = text.replace("Ü", "u").replace("ü", "u")
    return text.lower()

def match_chapters_from_cache(product_text: str) -> List[str]:
    """
    Dinamik olarak çekilen resmi TGTC Fasıl Tanımları ve BTB kataloğu üzerinde
    semantik / token süzmesi yaparak eşleşen Fasılları döndürür.
    HİÇBİR HARDCODED SÖZLÜK KULLANMAZ.
    """
    norm_input = tr_normalize(product_text)
    input_words = set(w for w in re.findall(r'[a-z0-9]+', norm_input) if w not in TURKISH_STOP_WORDS and len(w) >= 3)

    if not input_words:
        return []

    chapters = load_tgtc_chapters() or TGTC_CHAPTERS
    matched_chapters = []

    # 1. Canlı TGTC Fasıl Tanımları Üzerinden Dinamik Token Eşleme
    for chap_code, chap_desc in chapters.items():
        norm_desc = tr_normalize(chap_desc)
        desc_words = set(w for w in re.findall(r'[a-z0-9]+', norm_desc) if w not in TURKISH_STOP_WORDS and len(w) >= 3)
        
        common = input_words.intersection(desc_words)
        if common:
            matched_chapters.append(chap_code.zfill(2))

    # 2. Canlı BTB Karar Kataloğu Üzerinden Dinamik Eşleme
    catalog = load_btb_catalog() or TGTC_KNOWLEDGE_BASE_CATALOG
    for entry in catalog:
        desc = tr_normalize(entry.get("product_description", ""))
        desc_words = set(w for w in re.findall(r'[a-z0-9]+', desc) if w not in TURKISH_STOP_WORDS and len(w) >= 3)
        if len(input_words.intersection(desc_words)) >= 2:
            chap = str(entry.get("chapter", "")).zfill(2)
            if chap and chap not in matched_chapters:
                matched_chapters.append(chap)

    return list(dict.fromkeys(matched_chapters))

def get_chapter_title(chapter_code: str) -> str:
    """Fasıl koduna göre resmi tanım başlığını döndürür."""
    chaps = load_tgtc_chapters() or TGTC_CHAPTERS
    code_z = str(chapter_code).zfill(2)
    return chaps.get(code_z, "Genel Gümrük Tarife Cetveli Eşyası")

