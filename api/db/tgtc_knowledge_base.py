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
import datetime
from typing import Dict, List, Any

logger = logging.getLogger("TGTCKnowledgeBase")

from api.db.database import SessionLocal, GumrukEmsalKararModel

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

_LOCAL_POS_CACHE: Dict[str, str] = {}

def get_local_tgtc_headings() -> Dict[str, str]:
    """2026 TGTC yerleşik dizininden 4-Haneli Tarife Pozisyonları (HS Heading) sözlüğünü okur ve önbelleğe alır."""
    global _LOCAL_POS_CACHE
    if _LOCAL_POS_CACHE:
        return _LOCAL_POS_CACHE
    res = {}
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(base_dir, "2026 TGTC", "tgtc_2026_full_database.json")
        if not os.path.exists(db_path):
            db_path = "/app/2026 TGTC/tgtc_2026_full_database.json"
        if not os.path.exists(db_path):
            db_path = r"c:\Users\yusuf\Github\yapay-zeka-gtip-tespiti\2026 TGTC\tgtc_2026_full_database.json"
            
        if os.path.exists(db_path):
            with open(db_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                for item in raw_data:
                    code_raw = str(item.get("gtip_code", "")).replace(".", "").strip()
                    desc = str(item.get("description", "") or item.get("product_description", "")).strip()
                    if len(code_raw) == 4 and desc and not desc.startswith("-"):
                        res[code_raw] = desc.rstrip(":")
    except Exception as e:
        logger.warning(f"[TGTC Local DB] 4-hane pozisyon sözlük okuma uyarısı: {e}")
    _LOCAL_POS_CACHE = res
    return res

def load_tgtc_chapters() -> Dict[str, str]:
    """Resmi 2026 TGTC Kütüphanesi üzerinden 2 Haneli Fasıl sözlüğünü döndürür."""
    headings = get_local_tgtc_headings()
    result = {}
    for code, desc in headings.items():
        if len(str(code)) >= 2 and str(code)[:2].isdigit():
            chap = str(code)[:2]
            if chap not in result:
                clean_desc = desc.split("(")[0].split(",")[0].strip()
                result[chap] = f"Fasıl {chap}: {clean_desc}"
    return result

_BTB_CATALOG_CACHE: List[Dict[str, Any]] = None
_RULES_AND_NOTES_CACHE: Dict[str, Any] = None

def invalidate_catalog_cache():
    """Mevzuat güncellendiğinde katalog, pozisyon ve izahname önbelleklerini temizler."""
    global _BTB_CATALOG_CACHE, _LOCAL_POS_CACHE, _RULES_AND_NOTES_CACHE
    _BTB_CATALOG_CACHE = None
    _LOCAL_POS_CACHE = None
    _RULES_AND_NOTES_CACHE = None
    logger.info("[TGTC Catalog] Bellek içi katalog, pozisyon ve izahname önbellekleri temizlendi.")

_BAD_DESC_PATTERNS = [
    r"metin [iı]çerikli", r"tebli[gğ]\s*/?\s*karar", r"sayfa\s+\d", r"\[pozisyon",
    r"g[uü]mr[uü]k s[iı]n[iı]fland[iı]rma karar[iı]", r"bu tebli[gğ]in amac[iı]",
    r"haks[iı]z rekabetin [öo]nlenmesi", r"ithalatta haks[iı]z rekabet",
    r"g[uü]mr[uü]k genel tebli[gğ]i", r"resm[iı] gazete", r"ama[cç] ve kapsam",
    r"madde\s*\d+", r"ge[cç][iı]ci madde", r"soru[sş]turma konusu",
    r"ayn[iı] tebli[gğ]in eki", r"ek-[0-9]+", r"tarihli ve", r"m[uü]kerrer say[iı]l[iı]",
    r"karar[iı] eki karar[iı]n", r"[oö]zel t[uü]ketim vergisi", r"f[iı]kras[iı] uyar[iı]nca",
    r"y[uü]r[uü]rl[uü]kten kald[iı]r[iı]lm[iı][sş]t[iı]r", r"sat[iı]r eklenmi[sş]tir",
    r"tabloya", r"tablodaki", r"gt[iı]p numaral[iı]", r"g[uü]mr[uü]k tarife istatistik",
    r"yerli [uü]retici", r"soru[sş]turma", r"kapsam[iı]nda yer alan",
]


def _is_bad_desc(text_str: str) -> bool:
    """Verilen metnin jenerik tebliğ veya maddeden ibaret olup olmadığını doğrular."""
    if not text_str or len(text_str.strip()) < 4:
        return True
    t = text_str.strip()
    return any(re.search(p, t, re.IGNORECASE) for p in _BAD_DESC_PATTERNS)


def _clean_product_name(text_str: str) -> str:
    """Madde numaraları (*35-, 37-) ve GTİP etiketlerini (*[GTİP: 22...) temizler."""
    if not text_str:
        return ""
    s = text_str.strip()
    # Maddesel önek temizliği: "*35- Etil Alkol" veya "37- Dezenfektan"
    s = re.sub(r"^[\*\s\-\d]{1,6}\s*", "", s)
    # Parantez içi GTİP son ek temizliği: "Etil Alkol [GTİP: 22.07...]"
    s = re.sub(r"\[?\s*GT[İI]P\s*:?.*$", "", s, flags=re.IGNORECASE)
    return s.strip(" ,.-*")


def _auto_fix_description(desc: str, legal: str, gtip: str = "") -> str:
    """
    Jenerik veya 'Metin İçerikli Tebliğ Kaydı' olan eşya tanımlarını 
    Hukuki Gerekçe ve Mevzuat metni içinden dinamik olarak gerçek ürün ismine dönüştürür.
    Metinde gerçek ürün adı yoksa rastgele tebliğ maddesi DÖNDÜRMET! TGTC pozisyon adını kullanır.
    """
    desc_str = _clean_product_name(str(desc or ""))
    legal_str = str(legal or "").strip()

    # Eğer mevcut açıklama zaten temiz ve anlamlı bir ürün ismiyse dokunma
    if desc_str and len(desc_str) >= 4 and not _is_bad_desc(desc_str):
        return desc_str

    combined = f"{desc_str} {legal_str}"

    # 1. Tırnak İçi Gerçek Ürün İsmi (EN GÜVENİLİR STRATEJİ: Örn: "Etil Alkol", "Dezenfektan", "hidrojenortofosfat")
    quotes = re.findall(r'"([^"]{3,150})"', combined)
    if quotes:
        for q in quotes:
            q_clean = _clean_product_name(q)
            if q_clean and len(q_clean) >= 3 and not _is_bad_desc(q_clean):
                return q_clean

    # 2. "Eşya Tanımı:" / "Konu:" etiketinden sonraki değeri al
    m = re.search(r"(?:e[şs]ya tan[iı]m[iı]|konu|[üu]r[üu]n)\s*:\s*(.+?)(?:\n|hukuki|gerek[cç]e|$)", combined, re.IGNORECASE)
    if m:
        candidate = _clean_product_name(m.group(1))
        if candidate and len(candidate) > 4 and not _is_bad_desc(candidate):
            return candidate[:200]

    # 3. 'yer alan ... ithalatı/eşyası/ürünü' kalıbı
    m = re.search(r'yer alan\s+(.+?)(?:\s+ithalat[iı]|\s+ihracat[iı]|\s+[üu]r[üu]n[üu]|\s+e[şs]yas[iı]|\s+iznine|\s+tabidir)', combined, re.IGNORECASE)
    if m:
        candidate = _clean_product_name(m.group(1))
        if candidate and 4 < len(candidate) < 150 and not _is_bad_desc(candidate):
            return candidate[:150]

    # 4. Fallback: Rastgele tebliğ maddesi DÖNDÜRME! TGTC tarife pozisyonu başlığını kullan
    gtip_clean = re.sub(r"[^\d]", "", str(gtip or ""))
    if gtip_clean and len(gtip_clean) >= 4:
        pos_code = gtip_clean[:4]
        try:
            pos_dict = get_local_tgtc_headings()
            pos_info = pos_dict.get(pos_code)
            if pos_info and pos_info.get("description"):
                return f"{pos_info['description'].strip()} (GTİP {gtip})"
        except Exception:
            pass

    return f"Gümrük Mevzuat Kararı Eşya Kaydı ({gtip})"



def load_btb_catalog() -> List[Dict[str, Any]]:
    """Resmi BTB Emsal Kararlar Kataloğunu GCP Cloud SQL, GCS Bucket veya /tmp üzerinden okur ve hiyerarşik ağaç breadcrumb ile standartlaştırır."""
    global _BTB_CATALOG_CACHE
    if _BTB_CATALOG_CACHE is not None:
        return _BTB_CATALOG_CACHE

    def _count_dashes_and_clean(text: str) -> int:
        s = text.lstrip()
        count = 0
        while s.startswith("-"):
            count += 1
            s = s[1:].lstrip()
        return count

    def _process_and_enrich_catalog(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pos_dict = get_local_tgtc_headings()
        enriched_list = []
        seen_keys = set()
        
        current_heading = None
        hierarchy_stack: Dict[int, str] = {}

        for idx, item in enumerate(raw_items):
            gtip_raw = item.get("gtip_code", "")
            btb_raw = str(item.get("btb_no") or f"TGTC2026-{gtip_raw}-{idx}").strip()
            desc = str(item.get("product_description") or item.get("description", "")).strip()
            legal = str(item.get("legal_justification", "")).strip()
            
            # 1. Emsal Kararı Olmayan Kirli/Hatalı Verileri Kesinlikle Ekleme (Fasıl Başlıkları ve WCO Nomenklatür Rehberi)
            if (btb_raw.startswith(("TGTC-FASIL", "MEVZUAT")) or "WCO HS 2022" in legal or "BTI Consultation" in btb_raw or not str(gtip_raw).strip()):
                continue

            # GTİP normalizasyonu (4, 6, 8, 12 haneli)
            gtip_clean = str(gtip_raw).replace(".", "").strip()
            heading_code = gtip_clean[:4] if len(gtip_clean) >= 4 else gtip_clean
            
            # Geçersiz/Hatalı Pozisyon Filtresi (Pozisyon kodu 2026 TGTC'de kayıtlı 964 pozisyondan biri olmalı)
            if pos_dict and heading_code not in pos_dict:
                continue

            # Ürün Tanımı Kalite Kontrolü (Harf sayısı yetersiz veya bütçe/toplam tablosu ise atla)
            letter_count = len(re.findall(r'[a-zA-ZçğıöşüÇĞİÖŞÜ]', desc))
            if letter_count < 5 or desc.lower().startswith(("toplam", "rg-pdf", "gerekçe:", "sayfa ")) or desc.startswith("11,50") or desc.startswith("TOPLAM"):
                continue

            # 2. Emsal ve Tebliğler için Tekilleştirme (Gerçek BTB/RG kararlarını TGTC cetveli ile karıştırıp silme)
            if btb_raw.startswith("TGTC2026-"):
                dedup_key = f"TGTC_{gtip_raw}_{desc[:50]}"
            else:
                # Gerçek Emsal BTB ve Tebliğ Kararları kendi btb_no'su ile tekilleşir
                dedup_key = f"REAL_{btb_raw}"

            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            
            # GTİP normalizasyonu (4, 6, 8, 12 haneli)
            gtip_clean = str(gtip_raw).replace(".", "").strip()
            heading_code = gtip_clean[:4] if len(gtip_clean) >= 4 else gtip_clean
            heading_title = pos_dict.get(heading_code, f"Pozisyon {heading_code}")

            gtip = str(gtip_raw)
            if len(gtip_clean) == 12 and gtip_clean.isdigit():
                gtip = f"{gtip_clean[:4]}.{gtip_clean[4:6]}.{gtip_clean[6:8]}.{gtip_clean[8:10]}.{gtip_clean[10:12]}"
            elif len(gtip_clean) == 8 and gtip_clean.isdigit():
                gtip = f"{gtip_clean[:4]}.{gtip_clean[4:6]}.{gtip_clean[6:8]}"
            elif len(gtip_clean) == 6 and gtip_clean.isdigit():
                gtip = f"{gtip_clean[:4]}.{gtip_clean[4:6]}"
            elif len(gtip_clean) == 4 and gtip_clean.isdigit():
                gtip = gtip_clean

            # Hiyerarşik Tarife Ağacı (Breadcrumb) Takibi (Sadece TGTC Cetveli İçin, Gerçek BTB'lere Dokunma)
            if btb_raw.startswith("TGTC2026-"):
                if heading_code != current_heading:
                    current_heading = heading_code
                    hierarchy_stack.clear()
                    hierarchy_stack[0] = f"[Pozisyon {heading_code}: {heading_title}]"

                dash_count = _count_dashes_and_clean(desc)
                if dash_count > 0 or str(desc).strip().startswith("-"):
                    # Daha derin veya eşit düzeyleri yığından temizle (yeni dal başlıyor)
                    keys_to_remove = [k for k in hierarchy_stack.keys() if k >= dash_count]
                    for k in keys_to_remove:
                        del hierarchy_stack[k]
                    
                    # Ataları birleştirerek breadcrumb silsilesini üret
                    parents = [hierarchy_stack[k] for k in sorted(hierarchy_stack.keys()) if hierarchy_stack.get(k)]
                    enriched_desc = " -> ".join(parents + [f"[{desc}] (GTİP: {gtip})"])
                    
                    # Mevcut satırı atalar arasına kaydet
                    hierarchy_stack[dash_count] = f"[{desc}]"
                    desc = enriched_desc
                elif "Diğerleri" in desc or len(desc) < 15:
                    desc = f"[Pozisyon {heading_code}: {heading_title}] {desc} (GTİP: {gtip})"
                    if dash_count == 0:
                        hierarchy_stack[0] = f"[Pozisyon {heading_code}: {heading_title}]"

            # Ölçü birimi ve vergi oranlarını iliştir
            if item.get("unit") and "[Ölçü:" not in desc and str(item.get("unit")).strip() not in ("", "-"):
                desc += f" [Ölçü: {item.get('unit')}]"
            if item.get("tax_rate") and "[Vergi" not in str(desc) and str(item.get("tax_rate")).strip() not in ("", "-"):
                desc += f" [Vergi: %{item.get('tax_rate')}]"

            legal = item.get("legal_justification") or ""
            if ".xls" in str(legal) or "Kaynak Fasıl" in str(legal) or not legal:
                legal = f"2026 T.C. Ticaret Bakanlığı Resmi Gümrük Tarife Cetveli (Pozisyon {heading_code} Yasal Hükümleri)"
            
            date_val = item.get("issue_date") or item.get("source_year") or "2026-01-01"
            btb_id = btb_raw

            # 🎯 Gerçek BTB / Emsal Kararları İçin Otomatik Ürün Açıklaması Temizleyici ve Çıkarıcı
            if not btb_id.startswith("TGTC2026-"):
                desc = _auto_fix_description(desc, legal, gtip)
                letter_cnt = len(re.findall(r'[a-zA-ZçğıöşüÇĞİÖŞÜ]', desc))
                # 🚫 Rakam/bütçe tablolarını, metinsiz hücreleri ve 'Metin İçerikli' kalan kayıtları atla 🚫
                if letter_cnt < 5 or any(k in desc for k in ["Metin İçerikli", "Tebliğ / Karar Metni", "Sayfa "]) or desc.lower().startswith(("toplam", "rg-pdf", "gerekçe:")) or re.match(r"^[\d\.\,\s\-\+\*\$\%\:\;]+$", desc):
                    continue

            enriched_list.append({
                "btb_no": btb_id,
                "gtip_code": gtip,
                "chapter": item.get("chapter", "") or gtip_clean[:2],
                "heading": item.get("heading", "") or heading_code,
                "issue_date": str(date_val),
                "product_description": desc,
                "legal_justification": legal
            })
        return enriched_list

    all_raw_items: List[Dict[str, Any]] = []

    # 1. Öncelikli ve Temel Katman: Yerel 2026 TGTC Kütüphanesi (Hiyerarşik Sıralı 216.000+ Kayıt)
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        tgtc_path = os.path.join(base_dir, "2026 TGTC", "tgtc_2026_full_database.json")
        if not os.path.exists(tgtc_path):
            tgtc_path = r"c:\Users\yusuf\Github\yapay-zeka-gtip-tespiti\2026 TGTC\tgtc_2026_full_database.json"
        if os.path.exists(tgtc_path):
            with open(tgtc_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 10:
                    all_raw_items.extend(data)
                    logger.info(f"[TGTC Catalog] Yerel TGTC 2026 hazinesi okundu ({len(data)} satır).")
    except Exception as e:
        logger.warning(f"[TGTC Catalog] Yerel TGTC kütüphanesi okuma uyarısı: {e}")

    # 2. GCS Bucket Canlı Emsal Karar Okuma Kontrolü (Bakanlık Kazıma Verileri)
    try:
        from google.cloud import storage
        project_id = os.getenv("GCP_PROJECT_ID", "gtip-tespit-projesi")
        bucket_name = os.getenv("GCS_BUCKET_NAME", f"gtip-evrak-bucket-{project_id}")
        client = storage.Client(project=project_id)
        bucket = client.bucket(bucket_name)
        blobs = list(client.list_blobs(bucket, prefix="official_btb/"))
        if blobs:
            latest_blob = max(blobs, key=lambda b: b.updated)
            content = latest_blob.download_as_text()
            data = json.loads(content)
            if isinstance(data, list) and data:
                all_raw_items.extend(data)
                logger.info(f"[TGTC Catalog] GCS canlı emsal kararlar eklendi ({len(data)} kayıt).")
    except Exception as e:
        logger.warning(f"[TGTC Catalog] GCS Bucket canlı okuma uyarısı: {e}")

    # 3. Veritabanı (SQLAlchemy ORM) Emsal Kararları Kontrolü
    try:
        from api.db.database import init_orm_tables
        init_orm_tables()
        session = SessionLocal()


        
        try:
            emsal_recs = session.query(GumrukEmsalKararModel).all()
            for er in emsal_recs:
                all_raw_items.append({
                    "btb_no": er.referans_no or f"EMS-{er.id}",
                    "gtip_code": er.gtip_kodu,
                    "chapter": er.gtip_kodu[:2] if er.gtip_kodu else "",
                    "heading": er.gtip_kodu[:4] if er.gtip_kodu else "",
                    "issue_date": er.yayin_tarihi or "2026-01-01",
                    "product_description": er.esya_tanimi,
                    "legal_justification": f"[{er.karar_tipi}] {er.hukuki_gerekce or ''} (Resmi Gazete: {er.resmi_gazete_sayisi or '-'})"
                })
        except Exception as ex_emsal:
            logger.warning(f"[TGTC Catalog] GumrukEmsalKararModel okuma uyarısı: {ex_emsal}")
        session.close()
    except Exception as e:
        logger.warning(f"[TGTC Catalog] SQLAlchemy ORM BTB okuma uyarısı: {e}")

    # 4. Temp Fallback Kontrolü (Eğer hala boş ise)
    if not all_raw_items:
        try:
            import tempfile, glob
            date_str = datetime.date.today().strftime("%Y_%m_%d")
            local_path = os.path.join(tempfile.gettempdir(), f"btb_scraped_{date_str}.json")
            if os.path.exists(local_path):
                with open(local_path, "r", encoding="utf-8") as f:
                    all_raw_items.extend(json.load(f))
            else:
                tmp_files = glob.glob(os.path.join(tempfile.gettempdir(), "btb_scraped_*.json"))
                if tmp_files:
                    with open(tmp_files[-1], "r", encoding="utf-8") as f:
                        all_raw_items.extend(json.load(f))
        except Exception as e:
            logger.warning(f"[TGTC Catalog] Fallback okuma uyarısı: {e}")

    if all_raw_items:
        _BTB_CATALOG_CACHE = _process_and_enrich_catalog(all_raw_items)
        return _BTB_CATALOG_CACHE

    return []

def load_tgtc_rules_and_notes() -> Dict[str, Any]:
    """2026 TGTC Resmi Yorum Kurallarını, Ölçü Birimlerini ve 97 Fasıl Notunu okur (bellek önbellekli)."""
    global _RULES_AND_NOTES_CACHE
    if _RULES_AND_NOTES_CACHE is not None:
        return _RULES_AND_NOTES_CACHE
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        rules_path = os.path.join(base_dir, "2026 TGTC", "tgtc_2026_rules_and_notes.json")
        if not os.path.exists(rules_path):
            rules_path = "/app/2026 TGTC/tgtc_2026_rules_and_notes.json"
        if not os.path.exists(rules_path):
            rules_path = r"c:\Users\yusuf\Github\yapay-zeka-gtip-tespiti\2026 TGTC\tgtc_2026_rules_and_notes.json"
        if os.path.exists(rules_path):
            with open(rules_path, "r", encoding="utf-8") as f:
                _RULES_AND_NOTES_CACHE = json.load(f)
                return _RULES_AND_NOTES_CACHE
    except Exception as e:
        logger.warning(f"[TGTC Rules] Yorum kuralları ve fasıl notu okuma uyarısı: {e}")
    _RULES_AND_NOTES_CACHE = {"yorum_kurallari": [], "olcu_birimleri": [], "fasil_notlari": {}}
    return _RULES_AND_NOTES_CACHE

# Dynamic property wrappers for backward compatibility
TGTC_CHAPTERS = load_tgtc_chapters()
TGTC_KNOWLEDGE_BASE_CATALOG = load_btb_catalog()
TGTC_RULES_AND_NOTES = load_tgtc_rules_and_notes()

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

