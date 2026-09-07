"""
Resmî Gazete Gümrük Genel Tebliğleri ve Sınıflandırma Kararları Arşiv & Canlı ETL Tarayıcısı.

GCP Entegrasyonları:
- Cloud Storage (gs://gumruk-mevzuat-storage-us-central1/resmi_gazete_raw_pdfs/) -> Karar içeren ham PDF arşivi
- Cloud Storage (gs://gumruk-mevzuat-storage-us-central1/etl_state/archive_checkpoint.json) -> Dağıtık checkpoint durumu
- Vertex AI Gemini 3.5 Flash Lite -> Multimodal tablo ve GİR gerekçe ayrıştırma
- Vertex AI text-embedding-005 -> 768 boyutlu vektörleştirme
- Cloud SQL PostgreSQL -> Versiyonlu upsert (gumruk_emsal_kararlar)
"""

import io
import os
import re
import sys
import json
import time
import argparse
import datetime
import logging
import requests
import urllib3
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional

# Root directory path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from api.config import settings
from scripts.extract_official_gazette_exact import extract_tables_from_gazette_pdf, CustomsDecisionItem
from scripts.parse_rg_pdf_digital import upload_pdf_to_gcs

urllib3.disable_warnings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("RGPDFSpider")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
RG_BASE = "https://www.resmigazete.gov.tr"
CHECKPOINT_BLOB_PATH = "etl_state/archive_checkpoint.json"
LOCAL_CHECKPOINT_PATH = os.path.join(root_dir, ".etl_checkpoint.json")


# ==============================================================================
# CHECKPOINT & DURUM YÖNETİMİ
# ==============================================================================

def load_checkpoint() -> Dict[str, Any]:
    """GCS veya yerel dosyadan en son checkpoint durumunu okur."""
    default_state = {
        "last_processed_date": None,
        "total_processed_days": 0,
        "total_saved_records": 0,
        "last_updated_at": None
    }
    
    # 1. GCS'den oku
    bucket_name = getattr(settings, "GCS_BUCKET_NAME", "gumruk-mevzuat-storage-us-central1")
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(CHECKPOINT_BLOB_PATH)
        if blob.exists():
            data = json.loads(blob.download_as_text(encoding="utf-8"))
            logger.info(f"[Checkpoint] GCS'den okundu: Son işlenen tarih = {data.get('last_processed_date')}")
            return data
    except Exception as e:
        logger.debug(f"[Checkpoint] GCS okuma atlandı/hata: {e}")

    # 2. Yerel fallback oku
    if os.path.exists(LOCAL_CHECKPOINT_PATH):
        try:
            with open(LOCAL_CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"[Checkpoint] Yerelden okundu: Son işlenen tarih = {data.get('last_processed_date')}")
                return data
        except Exception:
            pass

    return default_state


def save_checkpoint(state: Dict[str, Any]):
    """Checkpoint durumunu hem GCS'e hem yerel dosyaya yazar."""
    state["last_updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state_json = json.dumps(state, ensure_ascii=False, indent=2)

    # 1. Yerel kaydet
    try:
        with open(LOCAL_CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            f.write(state_json)
    except Exception:
        pass

    # 2. GCS'e kaydet
    bucket_name = getattr(settings, "GCS_BUCKET_NAME", "gumruk-mevzuat-storage-us-central1")
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(CHECKPOINT_BLOB_PATH)
        blob.upload_from_string(state_json, content_type="application/json")
        logger.debug(f"[Checkpoint] GCS'e yazıldı: {state.get('last_processed_date')}")
    except Exception as e:
        logger.debug(f"[Checkpoint] GCS yazma hatası: {e}")


def upload_pdf_to_gcs(pdf_bytes: bytes, filename: str) -> Optional[str]:
    """
    Resmî Gazete PDF dosyasını Google Cloud Storage bucket'ına yükler
    ve doğrudan erişilebilir public HTTPS URL'sini döner.
    """
    if not pdf_bytes or len(pdf_bytes) < 100:
        return None
    try:
        from google.cloud import storage
        project_id = getattr(settings, "GCP_PROJECT_ID", "gumruk-mevzuat")
        bucket_name = getattr(settings, "GCS_BUCKET_NAME", "gumruk-mevzuat-storage-us-central1")
        client = storage.Client(project=project_id)
        bucket = client.bucket(bucket_name)
        blob_path = f"resmi_gazete_raw_pdfs/{filename}"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(pdf_bytes, content_type="application/pdf")

        https_url = f"https://storage.googleapis.com/{bucket_name}/{blob_path}"
        logger.info(f"📤 [GCS PDF Yüklendi] {https_url}")
        return https_url
    except Exception as e:
        logger.warning(f"⚠️ [GCS PDF Yükleme Hatası] ({filename}): {e}")
        return None


# ==============================================================================
# VEKTÖR & VERİTABANI KAYDI
# ==============================================================================

def generate_embedding_for_decision(text: str) -> Optional[List[float]]:
    """Vertex AI text-embedding-005 ile 768 boyutlu embedding üretir."""
    if not text:
        return None
    try:
        from google import genai
        project_id = getattr(settings, "GCP_PROJECT_ID", "gumruk-mevzuat")
        location = getattr(settings, "GCP_REGION", "us-central1")
        client = genai.Client(vertexai=True, project=project_id, location=location)
        res = client.models.embed_content(
            model="text-embedding-005",
            contents=text[:2000]
        )
        if res and hasattr(res, "embedding") and res.embedding:
            return res.embedding.values
        if res and hasattr(res, "embeddings") and res.embeddings:
            return res.embeddings[0].values
    except Exception as e:
        logger.debug(f"Embedding üretme hatası: {e}")
    return None


def save_decisions_to_cloud_sql(
    items: List[CustomsDecisionItem], 
    kaynak_url: str, 
    gcs_pdf_uri: Optional[str] = None,
    skip_embedding: bool = False
) -> int:
    """Çıkarılan sınıflandırma kararlarını Cloud SQL veritabanına kaydeder/günceller."""
    if not items:
        return 0

    try:
        from api.db.database import SessionLocal, GumrukEmsalKararModel, GumrukSiniflandirmaKarariModel

        session = SessionLocal()
        saved_count = 0

        batch_sinif_keys = set()
        for idx, it in enumerate(items, start=1):
            gtip = it.gtip_kodu.strip()
            clean = re.sub(r"[^\d]", "", gtip)
            if len(clean) < 6:
                continue

            chapter = clean[:2]
            yayin_tarihi = it.yayin_tarihi or datetime.date.today().strftime("%Y-%m-%d")
            ref_no = f"RG-DEC-{yayin_tarihi.replace('-', '')}-{clean}-N{it.karar_no or idx}"
            sinif_key = (gtip, yayin_tarihi)

            # Vektör Embedding
            embedding_vec = None
            if not skip_embedding:
                embed_text = f"GTİP: {gtip} | Eşya: {it.esya_tanimi} | Gerekçe: {it.hukuki_gerekce}"
                embedding_vec = generate_embedding_for_decision(embed_text)

            try:
                # 1. GumrukSiniflandirmaKarariModel Upsert
                existing_sinif = session.query(GumrukSiniflandirmaKarariModel).filter(
                    GumrukSiniflandirmaKarariModel.gtip_kodu == gtip,
                    GumrukSiniflandirmaKarariModel.yayin_tarihi == yayin_tarihi
                ).first()

                if existing_sinif or sinif_key in batch_sinif_keys:
                    if existing_sinif:
                        existing_sinif.esya_tanimi = (existing_sinif.esya_tanimi + " | " + it.esya_tanimi)[:1000]
                        existing_sinif.hukuki_gerekce = it.hukuki_gerekce[:1500]
                        existing_sinif.resmi_gazete_sayisi = it.resmi_gazete_sayisi or "-"
                        existing_sinif.kaynak_url = gcs_pdf_uri or kaynak_url
                else:
                    sinif_obj = GumrukSiniflandirmaKarariModel(
                        karar_tipi="SINIFLANDIRMA_KARARI",
                        gtip_kodu=gtip,
                        yayin_tarihi=yayin_tarihi,
                        resmi_gazete_sayisi=it.resmi_gazete_sayisi or "-",
                        esya_tanimi=it.esya_tanimi[:1000],
                        hukuki_gerekce=it.hukuki_gerekce[:1500],
                        kaynak_url=gcs_pdf_uri or kaynak_url
                    )
                    session.add(sinif_obj)
                    batch_sinif_keys.add(sinif_key)
                    saved_count += 1

                # 2. GumrukEmsalKararModel Upsert
                existing_emsal = session.query(GumrukEmsalKararModel).filter(
                    (GumrukEmsalKararModel.referans_no == ref_no) | 
                    ((GumrukEmsalKararModel.gtip_kodu == gtip) & (GumrukEmsalKararModel.yayin_tarihi == yayin_tarihi) & (GumrukEmsalKararModel.esya_tanimi == it.esya_tanimi[:1000]))
                ).first()

                if existing_emsal:
                    existing_emsal.referans_no = ref_no
                    existing_emsal.esya_tanimi = it.esya_tanimi[:1000]
                    existing_emsal.hukuki_gerekce = it.hukuki_gerekce[:1500]
                    existing_emsal.kaynak_url = gcs_pdf_uri or kaynak_url
                    if embedding_vec and hasattr(existing_emsal, "embedding"):
                        existing_emsal.embedding = embedding_vec
                else:
                    emsal_obj = GumrukEmsalKararModel(
                        karar_tipi="SINIFLANDIRMA_KARARI",
                        referans_no=ref_no,
                        yayin_tarihi=yayin_tarihi,
                        resmi_gazete_sayisi=it.resmi_gazete_sayisi or "-",
                        gtip_kodu=gtip,
                        chapter_code=chapter,
                        esya_tanimi=it.esya_tanimi[:1000],
                        hukuki_gerekce=it.hukuki_gerekce[:1500],
                        kaynak_url=gcs_pdf_uri or kaynak_url
                    )
                    if embedding_vec and hasattr(emsal_obj, "embedding"):
                        emsal_obj.embedding = embedding_vec
                    session.add(emsal_obj)

                session.commit()
            except Exception as e_item:
                session.rollback()
                logger.debug(f"[Cloud SQL] Karar kaydetme satır uyarısı: {e_item}")

        session.close()
        logger.info(f"✅ [Cloud SQL] {len(items)} karar başarıyla işlendi (Yeni eklenen: {saved_count}).")
        return saved_count
    except Exception as e:
        logger.error(f"[Cloud SQL] Veritabanı kayıt hatası: {e}", exc_info=True)
        return 0


# ==============================================================================
# GÜNLÜK FİHRİST & PDF TARAMA
# ==============================================================================

def scan_and_process_gazette_day(year: int, month: int, day: int, skip_embedding: bool = False) -> int:
    """
    Tek bir Resmî Gazete gününün fihristini ve eklerini tarar:
    1. İlgili Gümrük Tebliğlerini saptar.
    2. Ekli PDF'i indirip Gemini 3.5 Flash Lite ile multimodal tablo ayrıştırmasından geçirir.
    3. Karar bulunursa ham PDF'i GCS'e arşivler, kararları Cloud SQL'e kaydeder.
    """
    date_str = f"{year}{month:02d}{day:02d}"
    pub_date = f"{year}-{month:02d}-{day:02d}"
    index_url = f"{RG_BASE}/eskiler/{year}/{month:02d}/{date_str}.htm"

    total_saved = 0
    try:
        resp = requests.get(index_url, headers=HEADERS, verify=False, timeout=10)
        if resp.status_code != 200:
            return 0

        resp.encoding = "windows-1254"
        soup = BeautifulSoup(resp.text, "html.parser")

        # Resmî Gazete Sayısını Tespit Et (Örn: "Sayı : 31793")
        gazette_no = "-"
        body_text = soup.get_text()
        no_match = re.search(r"Sayı\s*:\s*(\d+)", body_text, re.IGNORECASE)
        if no_match:
            gazette_no = no_match.group(1)

        pdf_candidates = set()

        # Fihristteki linkleri tara
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            link_text = a.get_text(strip=True).lower()

            if href.endswith(".pdf"):
                full_pdf = href if href.startswith("http") else f"{RG_BASE}/eskiler/{year}/{month:02d}/{href}"
                pdf_candidates.add(full_pdf)

            elif href.endswith(".htm") and href != f"{date_str}.htm":
                full_htm = href if href.startswith("http") else f"{RG_BASE}/eskiler/{year}/{month:02d}/{href}"
                # İlgili gümrük tebliği anahtar kelimeleri
                if any(k in link_text for k in ["gümrük", "tarife", "sınıflandırma", "ithalatta haksız rekabet", "tebliğ", "karar"]):
                    try:
                        sub_resp = requests.get(full_htm, headers=HEADERS, verify=False, timeout=6)
                        if sub_resp.status_code == 200:
                            sub_resp.encoding = "windows-1254"
                            sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                            for sub_a in sub_soup.find_all("a", href=True):
                                sub_href = sub_a.get("href", "")
                                if sub_href.endswith(".pdf"):
                                    full_sub_pdf = sub_href if sub_href.startswith("http") else f"{RG_BASE}/eskiler/{year}/{month:02d}/{sub_href}"
                                    pdf_candidates.add(full_sub_pdf)
                    except Exception:
                        pass

        # Tespit edilen PDF'leri Multimodal olarak ayrıştır
        for pdf_url in pdf_candidates:
            try:
                pdf_resp = requests.get(pdf_url, headers=HEADERS, verify=False, timeout=15)
                if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1000:
                    # 1. Multimodal Ayrıştırma
                    extracted_items = extract_tables_from_gazette_pdf(
                        pdf_resp.content, 
                        pub_date=pub_date, 
                        gazette_no=gazette_no
                    )

                    if extracted_items:
                        logger.info(f"🎯 [KARAR BULUNDU] {pub_date} (Sayı: {gazette_no}) - {pdf_url}: {len(extracted_items)} karar tespit edildi!")
                        
                        # 2. Ham PDF'i Cloud Storage'a Yükle
                        pdf_name = pdf_url.split("/")[-1] or f"karar_{date_str}.pdf"
                        gcs_pdf_uri = upload_pdf_to_gcs(pdf_resp.content, f"{date_str}_{pdf_name}")
                        
                        # 3. Cloud SQL'e Kaydet
                        saved = save_decisions_to_cloud_sql(
                            extracted_items, 
                            kaynak_url=pdf_url, 
                            gcs_pdf_uri=gcs_pdf_uri,
                            skip_embedding=skip_embedding
                        )
                        total_saved += saved

            except Exception as pdf_e:
                logger.debug(f"PDF işleme hatası [{pdf_url}]: {pdf_e}")

    except Exception as e:
        logger.debug(f"Fihrist tarama hatası [{pub_date}]: {e}")

    return total_saved


# ==============================================================================
# ÇALIŞTIRMA MODLARI (ARCHIVE BACKFILL & DAILY CRON)
# ==============================================================================

def run_archive_backfill(
    start_date_str: str = "2020-01-01", 
    end_date_str: str = "2026-08-19",
    batch_size: int = 30,
    skip_embedding: bool = False
):
    """
    2020 - 2026 yılları arasındaki tüm Resmî Gazete günlerini parçalı (chunked)
    ve checkpoint mekanizmalı olarak tarar.
    """
    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()

    checkpoint = load_checkpoint()
    last_processed = checkpoint.get("last_processed_date")
    if last_processed:
        last_date = datetime.datetime.strptime(last_processed, "%Y-%m-%d").date()
        if last_date >= start_date and last_date < end_date:
            logger.info(f"🔄 Checkpoint devrede! Tarama {last_date + datetime.timedelta(days=1)} tarihinden devam ediyor.")
            start_date = last_date + datetime.timedelta(days=1)

    logger.info("=" * 70)
    logger.info(f"🚀 RESMÎ GAZETE ARŞİV TARAMASI BAŞLATILIYOR ({start_date} ➔ {end_date})")
    logger.info("=" * 70)

    current_date = start_date
    delta = datetime.timedelta(days=1)
    grand_total = checkpoint.get("total_saved_records", 0)
    days_processed = checkpoint.get("total_processed_days", 0)

    while current_date <= end_date:
        saved_today = scan_and_process_gazette_day(
            current_date.year, 
            current_date.month, 
            current_date.day,
            skip_embedding=skip_embedding
        )
        grand_total += saved_today
        days_processed += 1

        # Checkpoint periyodik kaydet
        if days_processed % batch_size == 0 or current_date == end_date:
            checkpoint_state = {
                "last_processed_date": current_date.strftime("%Y-%m-%d"),
                "total_processed_days": days_processed,
                "total_saved_records": grand_total
            }
            save_checkpoint(checkpoint_state)
            logger.info(f"📊 [Checkpoint] {current_date} kaydedildi. Toplam İşlenen Gün: {days_processed} | Toplam Karar: {grand_total}")

        current_date += delta
        time.sleep(0.05)

    logger.info("=" * 70)
    logger.info(f"🎉 ARŞİV TARAMASI TAMAMLANDI! Toplam {grand_total} sınıflandırma kararı veritabanına aktarıldı.")
    logger.info("=" * 70)


def run_daily_sync(days_back: int = 2, skip_embedding: bool = False) -> int:
    """
    Günlük gece yarısı Cloud Scheduler tetiklemesiyle çalışan hafif senkronizasyon.
    Son X günü (varsayılan: son 2 gün) tarar.
    """
    logger.info("=" * 70)
    logger.info(f"⏰ GÜNLÜK RESMÎ GAZETE SENKRONİZASYONU BAŞLATILIYOR (Son {days_back} Gün)")
    logger.info("=" * 70)

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days_back)
    delta = datetime.timedelta(days=1)

    current_date = start_date
    total_saved = 0

    while current_date <= end_date:
        logger.info(f"🔍 Günlük Tarama: {current_date.strftime('%Y-%m-%d')}")
        saved = scan_and_process_gazette_day(
            current_date.year, 
            current_date.month, 
            current_date.day,
            skip_embedding=skip_embedding
        )
        total_saved += saved
        current_date += delta

    logger.info(f"✅ Günlük tarama bitti. {total_saved} yeni sınıflandırma kararı işlendi.")
    return total_saved


# Geriye dönük uyumluluk takma adları (Backward Compatibility Aliases)
run_spider_2020_to_2026 = run_archive_backfill
run_spider_daily = run_daily_sync

# ==============================================================================
# CLI GİRİŞ NOKTASI
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resmî Gazete Gümrük Kararları ETL & Arşiv Tarayıcısı")
    parser.add_argument("--mode", choices=["archive", "daily"], default="archive", help="Çalışma modu: 'archive' (toplu) veya 'daily' (günlük)")
    parser.add_argument("--start-date", type=str, default="2020-01-01", help="Arşiv başlangıç tarihi (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default="2026-08-19", help="Arşiv bitiş tarihi (YYYY-MM-DD)")
    parser.add_argument("--batch-size", type=int, default=30, help="Checkpoint aralığı (gün)")
    parser.add_argument("--days-back", type=int, default=2, help="Günlük modda geriye dönük taranacak gün sayısı")
    parser.add_argument("--skip-embedding", action="store_true", help="Vektörleştirme adımını atla")
    args = parser.parse_args()

    if args.mode == "daily":
        run_daily_sync(days_back=args.days_back, skip_embedding=args.skip_embedding)
    else:
        run_archive_backfill(
            start_date_str=args.start_date,
            end_date_str=args.end_date,
            batch_size=args.batch_size,
            skip_embedding=args.skip_embedding
        )
