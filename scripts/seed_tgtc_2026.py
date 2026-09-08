"""
2026 Türk Gümrük Tarife Cetveli (TGTC) Statik Veri Tohumlama (Seed) & Vektörleştirme Betiği.
GCP us-central1 (Cloud SQL PostgreSQL + pgvector) ve yerel test ortamlarıyla %100 uyumludur.

Görevler:
1. 2026 TGTC 97 Fasıl, 4-haneli Pozisyon, 6-haneli Alt Pozisyon ve 12-haneli Milli GTİP Ağacını 'tgtc_gtip' tablosuna aktarır.
2. Fasıl Notlarını ve "Bu fasıl şunları kapsamaz..." dışlama hükümlerini 'tgtc_notes' tablosuna kaydeder.
3. GİR 1-6 Genel Yorum Kurallarını, Ölçü Birimlerini ve İzahnameleri 'tgtc_rules' tablosuna aktarır.
4. Vertex AI 'text-embedding-005' ile 768-boyutlu vektör temsillerini oluşturur ve pgvector sütunlarına yazar.
"""

import os
import sys
import json
import glob
import re
import time
import logging
from typing import List, Dict, Any, Optional

# Proje kök dizinini sys.path'e ekle
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SeedTGTC2026")

from sqlalchemy.orm import Session
from sqlalchemy import text
from api.db.database import (
    engine, init_orm_tables, SessionLocal,
    TgtcGtipModel, TgtcNoteModel, TgtcRuleModel
)
from api.config import settings

TGTC_DIR = os.path.join(ROOT_DIR, "2026 TGTC")


def get_embedding_batches(texts: List[str], batch_size: int = 100) -> List[Optional[List[float]]]:
    """
    Metinleri Vertex AI text-embedding-005 ile toplu (batch) olarak 768 boyutlu vektörlere dönüştürür.
    API anahtarı yoksa veya hata alınırsa None döner.
    """
    api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return [None] * len(texts)

    embeddings = []
    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                response = client.models.embed_content(
                    model=settings.EMBEDDING_MODEL,
                    contents=batch
                )
                if hasattr(response, 'embeddings') and response.embeddings:
                    for emb in response.embeddings:
                        embeddings.append(emb.values if hasattr(emb, 'values') else list(emb))
                else:
                    embeddings.extend([None] * len(batch))
            except Exception as e_batch:
                logger.warning(f"Batch embedding hatası [{i}:{i+len(batch)}]: {e_batch}")
                embeddings.extend([None] * len(batch))
                time.sleep(0.5)
    except Exception as e:
        logger.warning(f"Embedding istemci hatası: {e}")
        return [None] * len(texts)

    return embeddings


def seed_gir_and_auxiliary_rules(session: Session):
    """
    Genel Yorum Kuralları (GİR 1-6), Ölçü Birimleri ve Genel Açıklamaları tohumlar.
    """
    logger.info("--- 1. GİR Kuralları ve Ek Tablolar Tohumlanıyor ---")
    session.query(TgtcRuleModel).delete()
    session.commit()

    notes_json_path = os.path.join(TGTC_DIR, "tgtc_2026_rules_and_notes.json")
    gir_list = []
    measurement_list = []
    explanation_list = []

    if os.path.exists(notes_json_path):
        with open(notes_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            gir_list = data.get("yorum_kurallari", [])
            measurement_list = data.get("olcu_birimleri", [])
            explanation_list = data.get("aciklamalar", [])

    # Standart GİR 1-6 Kuralları Tanımları
    standard_gir_rules = [
        {"rule_number": "1", "title": "GİR Kuralı 1 - Pozisyon Metinleri ve Bölüm/Fasıl Notları", "text": "Bölüm, fasıl ve tali fasıl başlıkları sadece gösterici niteliktedir; yasal amaçlar için eşyanın tarifedeki yerinin saptanması, pozisyon metinlerine, ilgili herhangi bir bölüm veya fasıl notuna ve bu pozisyonlar veya notlar hükümlerinde aksi belirtilmedikçe, aşağıdaki kurallara göre yapılır."},
        {"rule_number": "2(a)", "title": "GİR Kuralı 2(a) - İmalı Bitirilmemiş veya Monte Edilmemiş Eşya", "text": "Tarifenin belirli bir pozisyonunda herhangi bir eşyaya yapılan bir atıf, bu eşyanın imali bitirilmemiş veya aksamı tamamlanmamış olanlarını da kapsar. Şu şartla ki, eşyanın gümrüğe sunulduğunda, imali bitirilmiş veya aksamı tamamlanmış eşyanın ayırt edici niteliğini içermesi gerekir. Keza, bir eşyaya yapılan atıf, imali bitirilmiş veya aksamı tamamlanmış eşya ile yukarıdaki hüküm gereğince böyle sayılan eşyanın sökük veya monte edilmemiş halde olanlarını da kapsar."},
        {"rule_number": "2(b)", "title": "GİR Kuralı 2(b) - Karışım veya Bileşimler", "text": "Tarifenin belirli bir pozisyonunda herhangi bir maddeye yapılan atıf, bu maddenin diğer maddelerle karışım veya bileşimlerini de içine alır. Aynı şekilde, belirli bir maddeden mamul bir eşyaya yapılan atıf, tamamen veya kısmen bu maddeden mamul eşyayı da kapsar. Birden fazla maddeden mamul eşyanın tarifedeki yeri 3 nolu kural prensiplerine göre saptanır."},
        {"rule_number": "3(a)", "title": "GİR Kuralı 3(a) - Özel Pozisyon Önceliği (Specificity)", "text": "Eşyayı en özel şekilde tanımlayan pozisyon, daha genel şekilde tanımlayan pozisyona göre öncelik alır. Bununla beraber, iki veya daha fazla pozisyonun her biri, karışım veya bileşim halindeki maddelerin sadece bir kısmına veya perakende satılacak hale getirilmiş takım halindeki eşyanın sadece bir parçasına atıfta bulunuyorsa; bu pozisyonlar eşit derecede özel sayılır."},
        {"rule_number": "3(b)", "title": "GİR Kuralı 3(b) - Esas Niteliğini Veren Madde (Essential Character)", "text": "3(a) kuralının uygulanmasıyla tarifedeki yeri saptanamayan karışımlar, farklı maddelerden müteşekkil veya farklı parçalardan birleşmiş eşya ve perakende satılacak hale getirilmiş takım halindeki eşya, uygulanabilmesi mümkün olduğu takdirde, eşyaya esas özelliğini veren madde veya parçaya göre sınıflandırılır."},
        {"rule_number": "3(c)", "title": "GİR Kuralı 3(c) - Son Pozisyon Kuralı", "text": "3(a) veya 3(b) kurallarının uygulanmasıyla tarifedeki yeri saptanamayan eşya, sırasıyla uygulanabilecek pozisyonların numara sırasına göre en sonuncusunda sınıflandırılır."},
        {"rule_number": "4", "title": "GİR Kuralı 4 - En Çok Benzeyen Eşya", "text": "Yukarıdaki kurallara göre sınıflandırılamayan eşya, kendisine en çok benzeyen eşyanın bulunduğu pozisyonda sınıflandırılır."},
        {"rule_number": "5(a)", "title": "GİR Kuralı 5(a) - Özel Kılıflar ve Muhafazalar", "text": "Fotoğraf makinesi muhafazası, müzik aleti mahfazası, silah kılıfı, çizim aleti kutusu gibi kaplar, özellikle ait oldukları eşyayı alacak şekilde şekillendirilmiş ve uzun süre kullanılmaya müsait olanlar beraber satıldıkları eşya ile birlikte sınıflandırılır."},
        {"rule_number": "5(b)", "title": "GİR Kuralı 5(b) - Ambalaj Maddeleri ve Kapları", "text": "İçindeki eşya ile birlikte sunulan ambalaj maddeleri ve kapları, normal olarak kullanıldıkları takdirde o eşya ile beraber sınıflandırılır."},
        {"rule_number": "6", "title": "GİR Kuralı 6 - Alt Pozisyon Kuralı", "text": "Yasal amaçlar için eşyanın herhangi bir pozisyonun alt pozisyonlarında sınıflandırılması, sadece aynı seviyedeki alt pozisyonların mukayese edilebilirliği şartıyla, alt pozisyon metinlerine ve bu alt pozisyonların notlarına göre saptanır."}
    ]

    for rule in standard_gir_rules:
        session.add(TgtcRuleModel(
            rule_type="GIR",
            rule_number=rule["rule_number"],
            title=rule["title"],
            text=rule["text"]
        ))

    # Ölçü Birimleri Ekleme
    for idx, m_text in enumerate(measurement_list):
        m_str = str(m_text).strip()
        if m_str and len(m_str) > 2:
            session.add(TgtcRuleModel(
                rule_type="MEASUREMENT",
                rule_number=str(idx + 1),
                title="Ölçü Birimi Tanımı",
                text=m_str
            ))

    # Genel Açıklamalar Ekleme
    for idx, exp_text in enumerate(explanation_list):
        exp_str = str(exp_text).strip()
        if exp_str and len(exp_str) > 5:
            session.add(TgtcRuleModel(
                rule_type="EXPLANATION",
                rule_number=str(idx + 1),
                title="Tarife Cetveli Açıklama Maddesi",
                text=exp_str
            ))

    session.commit()
    logger.info(f"GİR ve Ek Kurallar başarıyla yüklendi (Toplam: {session.query(TgtcRuleModel).count()} kayıt).")


def seed_chapter_notes_and_exclusions(session: Session, generate_embeddings: bool = True):
    """
    97 Faslın Bakanlık İzahname Notlarını ve "Bu fasıl şunları kapsamaz..." Dışlama Notlarını tohumlar.
    """
    logger.info("--- 2. Fasıl Notları ve Dışlama Hükümleri Tohumlanıyor ---")
    session.query(TgtcNoteModel).delete()
    session.commit()

    notes_json_path = os.path.join(TGTC_DIR, "tgtc_2026_rules_and_notes.json")
    notes_dict = {}
    if os.path.exists(notes_json_path):
        with open(notes_json_path, "r", encoding="utf-8") as f:
            ndata = json.load(f)
            notes_dict = ndata.get("fasil_notlari", {})

    # Ayrıca '2026 FASIL NOTLARI/' dizinindeki XLS dosyalarını kontrol et
    notes_dir = os.path.join(TGTC_DIR, "2026 FASIL NOTLARI")
    if os.path.exists(notes_dir):
        try:
            import pandas as pd
            xls_files = glob.glob(os.path.join(notes_dir, "Fasıl *.xls"))
            for f in xls_files:
                bname = os.path.basename(f)
                c_num_str = bname.replace("Fasıl ", "").replace(".xls", "").strip()
                try:
                    c_code = f"{int(c_num_str):02d}"
                    if c_code not in notes_dict:
                        df = pd.read_excel(f)
                        text_lines = df.iloc[:, 0].dropna().tolist()
                        notes_dict[c_code] = "\n".join(str(l).strip() for l in text_lines if str(l).strip())
                except Exception:
                    pass
        except ImportError:
            pass

    notes_to_insert = []
    for c_i in range(1, 98):
        c_code = f"{c_i:02d}"
        raw_text = notes_dict.get(c_code, f"Fasıl {c_code} Genel Gümrük Tarife Notları.")
        
        # 1. Genel Fasıl Notu
        notes_to_insert.append({
            "chapter_code": c_code,
            "note_type": "GENERAL",
            "title": f"Fasıl {c_code} Yasal ve İdari İzahname Notları",
            "text": raw_text
        })

        # 2. Dışlama Notu Ayrıştırması ("Bu fasıl şunları kapsamaz...", "Aşağıdakiler bu fasla dahil değildir...")
        exclusion_matches = []
        for line in raw_text.split('\n'):
            line_str = line.strip()
            if any(k in line_str.lower() for k in [
                "kapsamaz", "dahil değildir", "hariçtir", "ayakkabı", "oyuncak", "fasıl 64", "fasıl 95", "fasıl 85"
            ]):
                exclusion_matches.append(line_str)

        if exclusion_matches:
            exclusion_text = "\n".join(exclusion_matches)
            notes_to_insert.append({
                "chapter_code": c_code,
                "note_type": "EXCLUSION",
                "title": f"Fasıl {c_code} Yasal Dışlama Hükümleri",
                "text": exclusion_text
            })

    # Vektörleştirme (İsteğe bağlı ve toplu)
    if generate_embeddings and settings.GEMINI_API_KEY:
        logger.info(f"{len(notes_to_insert)} adet fasıl notu vektörleştiriliyor...")
        texts_to_embed = [n["title"] + ": " + n["text"][:1000] for n in notes_to_insert]
        embeddings = get_embedding_batches(texts_to_embed, batch_size=50)
        for i, n in enumerate(notes_to_insert):
            n["embedding"] = embeddings[i] if i < len(embeddings) else None
    else:
        for n in notes_to_insert:
            n["embedding"] = None

    for item in notes_to_insert:
        session.add(TgtcNoteModel(
            chapter_code=item["chapter_code"],
            note_type=item["note_type"],
            title=item["title"],
            text=item["text"],
            embedding=item["embedding"]
        ))

    session.commit()
    logger.info(f"Fasıl Notları başarıyla yüklendi (Toplam: {len(notes_to_insert)} kayıt).")


def seed_gtip_tree(session: Session, generate_embeddings: bool = False, max_embedding_limit: int = 1000):
    """
    2026 TGTC 97 Fasıl, 4-haneli Pozisyon, 6-haneli Alt Pozisyon ve 12-haneli GTİP Ağacını tohumlar.
    """
    logger.info("--- 3. 2026 TGTC Tarife Ağacı Tohumlanıyor ---")
    session.query(TgtcGtipModel).delete()
    session.flush()

    json_path = os.path.join(TGTC_DIR, "tgtc_2026_full_database.json")
    if not os.path.exists(json_path):
        logger.error(f"TGTC JSON veri dosyası bulunamadı: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    logger.info(f"Kaynak JSON dosyasında {len(entries)} adet GTİP satırı okundu.")

    # 1. Fasıl Başlıkları (01 - 97)
    existing_codes = set()
    rows_to_insert = []

    for c_i in range(1, 98):
        c_code = f"{c_i:02d}"
        rows_to_insert.append({
            "gtip_code": c_code,
            "level": "CHAPTER",
            "chapter_code": c_code,
            "parent_code": None,
            "description": f"Fasıl {c_code} - Resmi Gümrük Tarife Faslı",
            "tax_rate": "",
            "unit": "",
            "is_active": True
        })
        existing_codes.add(c_code)

    # 2. GTİP Kayıtlarını Hiyerarşik Seviyelerle Eşleştirme
    for item in entries:
        raw_code = str(item.get("gtip_code", "")).strip()
        clean_code = raw_code.replace(".", "").replace(" ", "").strip()
        if not clean_code:
            continue

        desc = str(item.get("description", "")).strip()
        tax = str(item.get("tax_rate", "")).strip()
        unit = str(item.get("unit", "")).strip()
        chap = clean_code[:2]

        code_len = len(clean_code)
        if code_len == 2:
            level = "CHAPTER"
            parent = None
        elif code_len == 4:
            level = "HEADING"
            parent = clean_code[:2]
        elif code_len == 6:
            level = "SUBHEADING"
            parent = clean_code[:4]
        else:
            level = "GTIP"
            parent = clean_code[:6] if code_len >= 6 else clean_code[:4]

        if clean_code not in existing_codes:
            rows_to_insert.append({
                "gtip_code": clean_code,
                "level": level,
                "chapter_code": chap,
                "parent_code": parent,
                "description": desc,
                "tax_rate": tax,
                "unit": unit,
                "is_active": True
            })
            existing_codes.add(clean_code)

    logger.info(f"Hazırlanan toplam tekil GTİP kayıt sayısı: {len(rows_to_insert)}")

    # 3. İsteğe Bağlı Vektörleştirme (Özellikle 4-haneli Pozisyonlar ve Örnek GTİP'ler)
    headings_and_subheadings = [r for r in rows_to_insert if r["level"] in ["CHAPTER", "HEADING", "SUBHEADING"]]
    if generate_embeddings and settings.GEMINI_API_KEY:
        logger.info(f"{len(headings_and_subheadings)} adet pozisyon/alt pozisyon vektörleştiriliyor...")
        texts_to_embed = [f"{r['gtip_code']} - {r['description']}" for r in headings_and_subheadings]
        embeddings = get_embedding_batches(texts_to_embed, batch_size=100)
        for i, r in enumerate(headings_and_subheadings):
            r["embedding"] = embeddings[i] if i < len(embeddings) else None

    # 4. Toplu Veritabanı Ekleme (Batch Insert)
    batch_size = 2000
    for idx in range(0, len(rows_to_insert), batch_size):
        batch = rows_to_insert[idx:idx + batch_size]
        for r in batch:
            session.add(TgtcGtipModel(
                gtip_code=r["gtip_code"],
                level=r["level"],
                chapter_code=r["chapter_code"],
                parent_code=r["parent_code"],
                description=r["description"],
                tax_rate=r["tax_rate"],
                unit=r["unit"],
                is_active=r["is_active"],
                embedding=r.get("embedding")
            ))
        # Ara flush belleği sınırlar; transaction ancak tüm cetvel başarıyla
        # yazıldıktan sonra commit edilir. Hata olursa eski cetvel rollback ile korunur.
        session.flush()
        logger.info(f"Eklenen GTİP satırı: {min(idx + batch_size, len(rows_to_insert))} / {len(rows_to_insert)}")

    session.commit()
    logger.info("2026 TGTC Tarife Ağacı başarıyla veritabanına aktarıldı.")


def run_full_seed(generate_embeddings: bool = False):
    """
    Tüm TGTC 2026 Statik Tohumlama Sürecini başlatır.
    """
    logger.info("==========================================================")
    logger.info("🚀 2026 TGTC STATİK VERİ TOHUMLAMA (SEED) BAŞLATILIYOR")
    logger.info(f"Hedef Bölge     : {settings.GCP_REGION}")
    logger.info(f"Hedef Cloud SQL : {settings.CLOUD_SQL_CONNECTION_NAME}")
    logger.info("==========================================================")

    # Bu kontrollü job zaten tam seed yapacak; init sırasında ikinci bir otomatik
    # seed başlatıp tabloyu iki kez yazma.
    os.environ["SKIP_TGTC_AUTO_SEED"] = "true"
    init_orm_tables()

    with SessionLocal() as session:
        seed_gir_and_auxiliary_rules(session)
        seed_chapter_notes_and_exclusions(session, generate_embeddings=generate_embeddings)
        seed_gtip_tree(session, generate_embeddings=generate_embeddings)

    logger.info("==========================================================")
    logger.info("✅ 2026 TGTC TOHUMLAMA İŞLEMİ EKSİKSİZ TAMAMLANDI!")
    logger.info("==========================================================")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="2026 TGTC Seed and Embedding Pipeline")
    parser.add_argument("--with-embeddings", action="store_true", help="Vertex AI text-embedding-005 vektörlerini de üret")
    args = parser.parse_args()

    run_full_seed(generate_embeddings=args.with_embeddings)
