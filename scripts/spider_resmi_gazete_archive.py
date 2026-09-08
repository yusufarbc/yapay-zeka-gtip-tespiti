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
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

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
TURKEY_TZ = ZoneInfo("Europe/Istanbul")


def today_in_turkey() -> datetime.date:
    """Cloud Run UTC kullansa da Resmî Gazete iş gününü Türkiye saatine göre hesaplar."""
    return datetime.datetime.now(TURKEY_TZ).date()


def _use_gcs_checkpoint() -> bool:
    return settings.ENVIRONMENT == "production" and not settings.USE_GCP_EMULATOR


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
    
    # 1. GCS'den oku (yalnızca production; test ve yerel import ağa çıkmaz)
    if _use_gcs_checkpoint():
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
    if _use_gcs_checkpoint():
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
            yayin_tarihi = it.yayin_tarihi or today_in_turkey().strftime("%Y-%m-%d")
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
    Tek bir Resmî Gazete gününün hem asıl hem de mükerrer (m1, m2, m3) sayılarını tarar:
    1. İlgili Gümrük Tebliğlerini ve eklerini saptar.
    2. Ekli PDF'i indirip Gemini 3.5 Flash Lite ile multimodal tablo ayrıştırmasından geçirir.
    3. Karar bulunursa ham PDF'i GCS'e arşivler, kararları Cloud SQL'e kaydeder.
    """
    date_str = f"{year}{month:02d}{day:02d}"
    pub_date = f"{year}-{month:02d}-{day:02d}"
    from scripts.scraper_function import ingest_gazette_document, is_customs_related
    
    # Asıl baskı ve mükerrer baskılar (m1, m2, m3)
    sub_editions = ["", "m1", "m2", "m3"]
    total_saved = 0

    for sub_ed in sub_editions:
        sub_key = f"{date_str}{sub_ed}"
        index_url = f"{RG_BASE}/eskiler/{year}/{month:02d}/{sub_key}.htm"
        
        try:
            resp = requests.get(index_url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue

            resp.encoding = "windows-1254"
            soup = BeautifulSoup(resp.text, "html.parser")

            # Resmî Gazete Sayısını Tespit Et (Örn: "Sayı : 31793")
            gazette_no = "-"
            body_text = soup.get_text()
            no_match = re.search(r"Sayı\s*:\s*(\d+)", body_text, re.IGNORECASE)
            if no_match:
                base_no = no_match.group(1)
                gazette_no = f"{base_no} ({sub_ed.upper()})" if sub_ed else base_no
            elif sub_ed:
                gazette_no = f"Mükerrer {sub_ed[1:]}"

            pdf_candidates = set()
            related_html_documents: Dict[str, str] = {}

            # Fihristteki linkleri tara
            for a in soup.find_all("a", href=True):
                href = a.get("href", "").strip()
                link_context = a.parent.get_text(" ", strip=True) if a.parent else a.get_text(" ", strip=True)

                if href.lower().endswith(".pdf"):
                    # Fihristteki ilgisiz yüzlerce PDF'i Gemini'ye göndermemek için bağlam filtresi uygula.
                    if is_customs_related(link_context):
                        pdf_candidates.add(urljoin(index_url, href))

                elif href.lower().endswith((".htm", ".html")) and href != f"{sub_key}.htm":
                    full_htm = urljoin(index_url, href)
                    if is_customs_related(link_context):
                        try:
                            sub_resp = requests.get(full_htm, headers=HEADERS, timeout=12)
                            if sub_resp.status_code == 200:
                                sub_resp.encoding = "windows-1254"
                                related_html_documents[full_htm] = sub_resp.text
                                sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                                for sub_a in sub_soup.find_all("a", href=True):
                                    sub_href = sub_a.get("href", "").strip()
                                    if sub_href.lower().endswith(".pdf"):
                                        pdf_candidates.add(urljoin(full_htm, sub_href))
                        except Exception as html_fetch_error:
                            logger.debug(f"Mevzuat HTML indirme hatası [{full_htm}]: {html_fetch_error}")

            # Gümrük mevzuatını yalnızca sınıflandırma kararı olarak değil,
            # MADDE hiyerarşisiyle de idempotent biçimde Cloud SQL'e kaydet.
            for document_url, raw_html in related_html_documents.items():
                try:
                    ingest_result = ingest_gazette_document(
                        raw_html=raw_html,
                        source_url=document_url,
                        pub_date=pub_date,
                        gazette_no=gazette_no,
                        skip_embedding=skip_embedding,
                    )
                    total_saved += int(ingest_result.get("inserted_articles", 0))
                except Exception as article_error:
                    logger.warning(f"Mevzuat maddeleri kaydedilemedi [{document_url}]: {article_error}")

            # Tespit edilen PDF'leri Multimodal olarak ayrıştır
            for pdf_url in pdf_candidates:
                try:
                    pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=30)
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
                            pdf_name = pdf_url.split("/")[-1] or f"karar_{sub_key}.pdf"
                            gcs_pdf_uri = upload_pdf_to_gcs(pdf_resp.content, f"{sub_key}_{pdf_name}")
                            
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
            logger.debug(f"Fihrist tarama hatası [{pub_date} {sub_ed}]: {e}")

    return total_saved


# ==============================================================================
# ÇALIŞTIRMA MODLARI (ARCHIVE BACKFILL & DAILY CRON)
# ==============================================================================

def run_archive_backfill(
    start_date_str: Optional[str] = None, 
    end_date_str: Optional[str] = None,
    batch_size: int = 30,
    skip_embedding: bool = False
):
    """
    Son 6 yıllık dinamik pencere (varsayılan) veya belirtilen tarih aralığındaki tüm
    Resmî Gazete günlerini parçalı (chunked), mükerrer destekli ve hataya dayanıklı checkpoint
    mekanizmasıyla tarar.
    """
    if end_date_str:
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    else:
        end_date = today_in_turkey()

    if start_date_str:
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    else:
        # Tam takvim yılı hesabı: artık yılları 6*365 yaklaşımıyla eksik bırakma.
        try:
            start_date = end_date.replace(year=end_date.year - 6)
        except ValueError:  # 29 Şubat -> hedef yılda 28 Şubat
            start_date = end_date.replace(year=end_date.year - 6, day=28)

    checkpoint = load_checkpoint()
    last_processed = checkpoint.get("last_processed_date")
    if last_processed:
        try:
            last_date = datetime.datetime.strptime(last_processed, "%Y-%m-%d").date()
            if start_date <= last_date < end_date:
                logger.info(f"🔄 Checkpoint devrede! Tarama {last_date + datetime.timedelta(days=1)} tarihinden devam ediyor.")
                start_date = last_date + datetime.timedelta(days=1)
        except Exception as cp_e:
            logger.warning(f"Checkpoint tarihi ayrıştırma uyarısı: {cp_e}")

    logger.info("=" * 70)
    logger.info(f"🚀 RESMÎ GAZETE DİNAMİK ARŞİV TARAMASI ({start_date} ➔ {end_date})")
    logger.info("=" * 70)

    current_date = start_date
    delta = datetime.timedelta(days=1)
    grand_total = checkpoint.get("total_saved_records", 0)
    days_processed = checkpoint.get("total_processed_days", 0)
    consecutive_errors = 0

    while current_date <= end_date:
        try:
            saved_today = scan_and_process_gazette_day(
                current_date.year, 
                current_date.month, 
                current_date.day,
                skip_embedding=skip_embedding
            )
            grand_total += saved_today
            days_processed += 1
            consecutive_errors = 0

            # Checkpoint periyodik kaydet (sadece başarılı işlenen güne kadar ilerletir)
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

        except Exception as e_day:
            logger.error(f"❌ [{current_date}] Tarama günü hatası: {e_day}")
            consecutive_errors += 1
            if consecutive_errors >= 3:
                # Tarihi ilerletmek checkpoint'in hatalı günü sonsuza kadar atlamasına yol açar.
                # Job başarısız olsun; Cloud Run retry aynı günü son checkpoint'ten yeniden işler.
                raise RuntimeError(
                    f"{current_date} tarihi 3 denemede işlenemedi; eksik gün bırakmamak için arşiv durduruldu."
                ) from e_day
            time.sleep(2.0)
            continue

    logger.info("=" * 70)
    logger.info(f"🎉 ARŞİV TARAMASI TAMAMLANDI! Toplam {grand_total} mevzuat/karar kaydı veritabanına aktarıldı.")
    logger.info("=" * 70)


def run_daily_sync(days_back: int = 3, skip_embedding: bool = False) -> int:
    """
    Günlük gece yarısı Cloud Scheduler tetiklemesiyle çalışan hafif senkronizasyon.
    Son X günü (varsayılan: son 3 gün, asıl + mükerrer) tarar.
    """
    logger.info("=" * 70)
    logger.info(f"⏰ GÜNLÜK RESMÎ GAZETE SENKRONİZASYONU BAŞLATILIYOR (Son {days_back} Gün - Asıl + Mükerrer)")
    logger.info("=" * 70)

    end_date = today_in_turkey()
    requested_days = max(1, days_back)
    start_date = end_date - datetime.timedelta(days=requested_days - 1)
    delta = datetime.timedelta(days=1)

    current_date = start_date
    total_saved = 0

    while current_date <= end_date:
        logger.info(f"🔍 Günlük Tarama: {current_date.strftime('%Y-%m-%d')}")
        try:
            saved = scan_and_process_gazette_day(
                current_date.year, 
                current_date.month, 
                current_date.day,
                skip_embedding=skip_embedding
            )
            total_saved += saved
        except Exception as e_day:
            logger.warning(f"Günlük tarama günü uyarısı [{current_date}]: {e_day}")

        current_date += delta

    logger.info(f"✅ Günlük tarama bitti. {total_saved} yeni mevzuat/karar kaydı işlendi.")
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
    parser.add_argument("--start-date", type=str, default=None, help="Arşiv başlangıç tarihi (YYYY-MM-DD, varsayılan: 6 yıl önce)")
    parser.add_argument("--end-date", type=str, default=None, help="Arşiv bitiş tarihi (YYYY-MM-DD, varsayılan: bugün)")
    parser.add_argument("--batch-size", type=int, default=30, help="Checkpoint aralığı (gün)")
    parser.add_argument("--days-back", type=int, default=3, help="Günlük modda geriye dönük taranacak gün sayısı")
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
