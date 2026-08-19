import io
import os
import sys
import re
import logging
import requests
import urllib3
import pdfplumber
from typing import List, Dict, Any

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

urllib3.disable_warnings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PDFDigitalParser")

def clean_gtip(raw_code: str) -> str:
    """GTİP kodundaki noktaları, boşlukları ve karakterleri temizler."""
    if not raw_code:
        return ""
    cleaned = re.sub(r"[^\d]", "", str(raw_code).strip())
    # GTİP gümrük standartlarında 6, 8, 10 veya 12 haneli olur
    return cleaned if len(cleaned) in [6, 8, 10, 12] else ""

def is_date_string(text: str) -> bool:
    if not text:
        return False
    if re.search(r'\b(0?[1-9]|[12][0-9]|3[01])[\./](0?[1-9]|1[0-2])[\./](19|20)\d\d\b', text):
        return True
    if re.search(r'\b(19|20)\d\d[\./-](0?[1-9]|1[0-2])[\./-](0?[1-9]|[12][0-9]|3[01])\b', text):
        return True
    return False

def format_gtip(clean_code: str) -> str:
    """Temiz 6, 8, 10 veya 12 haneli kodu XX.XX.XX.XX.XX.XX formatına sokar."""
    padded = clean_code.ljust(12, '0')
    return f"{padded[0:2]}.{padded[2:4]}.{padded[4:6]}.{padded[6:8]}.{padded[8:10]}.{padded[10:12]}"

def extract_gtip_records_from_digital_pdf(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Doğrudan seçilebilir metin/tablo barındıran dijital PDF'lerden 
    GTİP, Eşya Tanımı ve Gerekçe verilerini süzmektedir.
    """
    from api.db.tgtc_knowledge_base import get_local_tgtc_headings
    valid_headings = set(get_local_tgtc_headings().keys())

    records = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text_content = page.extract_text() or ""
                page_lower = text_content.lower()
                
                # SAYFA BAZLI KONTROL: Sayfada Gümrük, Tarife veya GTİP geçmiyorsa o sayfayı tamamen atla!
                if not any(k in page_lower for k in ["gtip", "gtıp", "g.t.i.p", "tarife", "eşya", "pozisyon"]):
                    continue
                    
                tables = page.extract_tables()
                
                # --- YÖNTEM A: Tablo Yapısındaki Sınıflandırma Kararları ---
                if tables:
                    for table in tables:
                        if not table:
                            continue
                        for row in table:
                            if not row or len(row) < 2:
                                continue
                            
                            # Satır hücrelerinde GTİP kalıbı ara
                            for idx, cell in enumerate(row):
                                if not cell:
                                    continue
                                
                                cell_str = str(cell).strip()
                                if is_date_string(cell_str):
                                    continue
                                # Yalnızca strict GTİP formatına benzeyen hücreleri kabul et (Örn: 8517.71, 8517.71.00.00.00)
                                if not re.match(r"^\d{4}\.\d{2}", cell_str):
                                    continue
                                    
                                gtip_candidate = clean_gtip(cell_str)
                                if gtip_candidate and gtip_candidate[:4] in valid_headings:
                                    # Diğer hücreleri filtrele (sıra nosu veya boş olmayan anlamlı hücreler)
                                    other_cells = []
                                    for c_idx, c in enumerate(row):
                                        if c_idx == idx or not c:
                                            continue
                                        c_str = str(c).replace("\n", " ").strip()
                                        # Sıra no veya sadece rakam/tire olan hücreleri atla (örn: "1 – ", "2")
                                        if re.match(r"^\s*[\d\.\–\-\s]+\s*$", c_str) and len(c_str) < 10:
                                            continue
                                        other_cells.append(c_str)

                                    product_desc = ""
                                    reasoning = ""
                                    if len(other_cells) == 1:
                                        product_desc = other_cells[0]
                                        reasoning = other_cells[0]
                                    elif len(other_cells) >= 2:
                                        product_desc = other_cells[0]
                                        reasoning = " | ".join(other_cells[1:])

                                    product_desc_clean = str(product_desc).replace("\n", " ").strip()
                                    desc_lower = product_desc_clean.toLowerCase() if hasattr(product_desc_clean, 'toLowerCase') else product_desc_clean.lower()
                                    
                                    # Harf sayısı ve bütçe/rakam tablosu süzgeci (Örn: "11,50", "3.894.000,00", "TOPLAM" satırlarını atla)
                                    letter_count = len(re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]", product_desc_clean))
                                    if letter_count < 5 or desc_lower.startswith(("toplam", "gerekçe:", "sayfa ")) or re.match(r"^[\d\.\,\s]+$", product_desc_clean):
                                        continue

                                    records.append({
                                        "gtip_kodu": format_gtip(gtip_candidate),
                                        "raw_gtip": gtip_candidate,
                                        "esyain_tanimi": product_desc_clean,
                                        "hukuki_gerekce": str(reasoning).replace("\n", " ").strip(),
                                        "sayfa_no": page_num
                                    })
                                    break
                
                # --- YÖNTEM B: Düz Metin Paragrafı / Madde Şeklindeki Tebliğler ---
                if text_content:
                    # Metni paragraflara / maddelere ayır (MADDE X veya çift alt satır bazlı)
                    paragraphs = re.split(r"\n(?=MADDE\s+\d+|\(\d+\)|\n)", text_content)
                    
                    for para in paragraphs:
                        para_clean = para.strip()
                        if not para_clean or len(para_clean) < 10:
                            continue
                            
                        # Gümrük/Tarife ile ilgisi yoksa atla (Örn. Tarih veya Üniversite ilanı numaraları)
                        if not any(k in para_clean.lower() for k in ["gtip", "gtıp", "g.t.i.p", "tarife", "eşya", "pozisyon"]):
                            continue
                            
                        # Paragraf içinde 6-12 haneli kesin noktalı GTİP kalıpları ara
                        matches = re.finditer(r"\b(\d{4}\.\d{2}(?:\.\d{2}){0,3})\b", para_clean)
                        for m in matches:
                            raw_match = m.group(0)
                            if is_date_string(raw_match) or is_date_string(para_clean):
                                continue
                            gtip_code = clean_gtip(raw_match)
                            if gtip_code and len(gtip_code) in [6, 8, 10, 12] and gtip_code[:4] in valid_headings:
                                formatted = format_gtip(gtip_code)
                                if not any(r["gtip_kodu"] == formatted for r in records):
                                    # 1. Tırnak içindeki ürün isimlerini bul (Örn: "gazla çalışan anında su ısıtıcılar" ürününe)
                                    quote_matches = re.findall(r'"([^"]{4,200})"', para_clean)
                                    extracted_desc = ""
                                    if quote_matches:
                                        # En uzun tırnak içi metni al (eşya tanımı genelde daha uzundur)
                                        extracted_desc = max(quote_matches, key=len).strip()
                                    else:
                                        # 2. Tırnak yoksa GTİP kodunu içeren anlamlı cümleyi al
                                        sentences = [s.strip() for s in re.split(r'[.;\n]', para_clean) if len(s.strip()) > 10 and (gtip_code in clean_gtip(s) or 'ürün' in s.lower() or 'eşya' in s.lower() or 'cinsi' in s.lower())]
                                        if sentences:
                                            # En anlamlı cümleyi bul
                                            extracted_desc = sentences[0][:250]
                                        else:
                                            extracted_desc = para_clean[:250]
                                            
                                    # Temizleme ve Doğrulama
                                    extracted_desc = extracted_desc.replace("\n", " ").replace("  ", " ").strip()
                                    letter_count = len(re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]", extracted_desc))
                                    if letter_count < 10 or extracted_desc.lower().startswith(("toplam", "sayfa ")):
                                        continue # Çok kısa veya anlamsız açıklamaları yoksay

                                    records.append({
                                        "gtip_kodu": formatted,
                                        "raw_gtip": gtip_code,
                                        "esyain_tanimi": extracted_desc,
                                        "hukuki_gerekce": para_clean.replace("\n", " ").strip(),
                                        "sayfa_no": page_num
                                    })

    except Exception as e:
        logger.error(f"PDF Parse Hatası: {e}")

    return records

def upload_pdf_to_gcs(pdf_bytes: bytes, filename: str, gcs_folder: str = "resmi_gazete_raw_pdfs") -> Optional[str]:
    """
    Sınıflandırma kararı içeren Resmî Gazete PDF'ini GCP Cloud Storage'a yükler ve gs:// URI döndürür.
    """
    bucket_name = os.getenv("GCS_BUCKET_NAME", "gtip-storage-west4")
    blob_name = f"{gcs_folder}/{filename}"
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(pdf_bytes, content_type="application/pdf")
        gcs_uri = f"gs://{bucket_name}/{blob_name}"
        logger.info(f"💾 Resmî Gazete PDF'i Cloud Storage'a arşivlendi: {gcs_uri}")
        return gcs_uri
    except Exception as e:
        logger.warning(f"GCS PDF yükleme hatası ({blob_name}): {e}")
        return None

def save_to_database_orm(parsed_records: List[Dict[str, Any]], kaynak_url: str, yayin_tarihi: str, gcs_pdf_uri: Optional[str] = None):
    """
    Parse edilen kayıtları SQLAlchemy ORM vasıtasıyla Cloud SQL veritabanına aktarır.
    """
    if not parsed_records:
        return 0

    try:
        from api.db.database import SessionLocal, GumrukEmsalKararModel
        from api.db.gcp_emulator import OfficialBTBModel

        session = SessionLocal()
        saved_count = 0

        for idx, rec in enumerate(parsed_records, start=1):
            gtip = rec["gtip_kodu"]
            clean = rec["raw_gtip"]
            page_no = rec.get("sayfa_no", 1)
            
            chapter = clean[:2]
            heading = clean[:4]
            hs6 = clean[:6]
            cn8 = clean[:8] if len(clean) >= 8 else clean[:6].ljust(8, '0')

            btb_no = f"RG-PDF-{yayin_tarihi.replace('-', '')}-{clean}-P{page_no}-{idx}"

            # Çakışma kontrolü ve kaydetme (OfficialBTBModel)
            existing = session.query(OfficialBTBModel).filter(OfficialBTBModel.btb_no == btb_no).first()
            if existing:
                existing.product_description = rec["esyain_tanimi"][:500] if rec["esyain_tanimi"] else existing.product_description
                existing.legal_justification = rec["hukuki_gerekce"][:1500] if rec["hukuki_gerekce"] else existing.legal_justification
            else:
                obj = OfficialBTBModel(
                    btb_no=btb_no,
                    gtip_code=gtip,
                    hs6_code=hs6,
                    cn8_code=cn8,
                    chapter=chapter,
                    heading=heading,
                    issue_date=yayin_tarihi,
                    product_description=rec["esyain_tanimi"][:500] if rec["esyain_tanimi"] else "Gümrük Sınıflandırma Kararı",
                    legal_justification=f"Resmî Gazete PDF ({kaynak_url}) | GCS: {gcs_pdf_uri or '-'} | Gerekçe: {rec['hukuki_gerekce'][:1500]}",
                    source="RG_PDF_DIGITAL",
                    is_active=True
                )
                session.add(obj)
                saved_count += 1

            # Çakışma kontrolü ve kaydetme (GumrukEmsalKararModel)
            existing_emsal = session.query(GumrukEmsalKararModel).filter(GumrukEmsalKararModel.referans_no == btb_no).first()
            if not existing_emsal:
                emsal_obj = GumrukEmsalKararModel(
                    karar_tipi="SINIFLANDIRMA_KARARI",
                    referans_no=btb_no,
                    yayin_tarihi=yayin_tarihi,
                    resmi_gazete_sayisi=rec.get("resmi_gazete_sayisi", "-"),
                    gtip_kodu=gtip,
                    esya_tanimi=rec["esyain_tanimi"][:500] if rec["esyain_tanimi"] else "Gümrük Sınıflandırma Kararı",
                    hukuki_gerekce=rec['hukuki_gerekce'][:1500] if rec.get('hukuki_gerekce') else "",
                    kaynak_url=gcs_pdf_uri or kaynak_url
                )
                session.add(emsal_obj)

        session.commit()
        session.close()
        logger.info(f"✅ {saved_count} yeni kayıt veritabanına işlendi.")
        return saved_count
    except Exception as e:
        logger.error(f"DB Kayıt Hatası: {e}")
        return 0

