"""
GCP Vertex AI Resmi Gazete (2020-2026) Bulk Extraction ve Cloud SQL Boru Hattı.

Süreç:
1. 2020 - 2026 yılları arasındaki tüm Resmî Gazete sayılarını (HTML ve PDF ekleri) GCP üzerinde tarar.
2. Çekilen ham metinleri Vertex AI (Gemini 3.6 Flash / Pydantic) ile konum işaretlemesine tabi tutar.
3. Python deterministik kopyalayıcı ile harfi harfine (exact-match) mevzuat maddelerini süzüp Cloud SQL PostgreSQL veritabanına UPSERT eder.
"""

import os
import sys
import re
import datetime
import argparse
import logging
import requests
import urllib3
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

urllib3.disable_warnings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GCPBulkExtractor2020_2026")

from api.config import settings
from api.db.database import SessionLocal, init_orm_tables
from scripts.extract_official_gazette_exact import extract_and_save_official_gazette, find_decision_boundaries

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
RG_BASE = "https://www.resmigazete.gov.tr"


def fetch_official_gazette_day_text(year: int, month: int, day: int) -> Optional[str]:
    """
    Belirtilen günün Resmi Gazete fihrist sayfasını (Normal + Mükerrer) ve içerisindeki tebliğ sayfalarını HTML metin olarak toplar.
    """
    date_str = f"{year}{month:02d}{day:02d}"
    pub_date = f"{year}-{month:02d}-{day:02d}"
    
    # Normal + Mükerrer Resmî Gazete Fihrist URL'leri
    candidate_index_urls = [
        f"{RG_BASE}/eskiler/{year}/{month:02d}/{date_str}.htm",
        f"{RG_BASE}/eskiler/{year}/{month:02d}/{date_str}M1.htm",
        f"{RG_BASE}/eskiler/{year}/{month:02d}/{date_str}M2.htm",
    ]

    combined_text = []
    sub_urls = set()

    for index_url in candidate_index_urls:
        try:
            resp = requests.get(index_url, headers=HEADERS, verify=False, timeout=8)
            if resp.status_code != 200:
                continue

            resp.encoding = 'windows-1254'
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            page_text = soup.get_text(separator="\n")
            if any(k in page_text.lower() for k in ["gümrük", "tarife", "gtip", "sınıflandırma", "tebliğ", "btb"]):
                combined_text.append(f"--- RESMİ GAZETE {pub_date} FİHRİST METNİ ({index_url}) ---\n" + page_text)

            # Tebliğ ve Karar alt HTML linklerini topla (Örn: 20220329M1-1.htm)
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                text = a.get_text(strip=True).lower()
                if href.endswith('.htm') and href not in [f"{date_str}.htm", f"{date_str}M1.htm", f"{date_str}M2.htm"]:
                    if any(k in text for k in ['gümrük', 'tarife', 'sınıf', 'sinif', 'tebliğ', 'tebli', 'karar']) or "m1-" in href.lower():
                        full_url = href if href.startswith('http') else f"{RG_BASE}/eskiler/{year}/{month:02d}/{href}"
                        sub_urls.add(full_url)
        except Exception as e_idx:
            logger.debug(f"Fihrist indirme uyarısı [{index_url}]: {e_idx}")

    for sub_url in sub_urls:
        try:
            sub_resp = requests.get(sub_url, headers=HEADERS, verify=False, timeout=8)
            if sub_resp.status_code == 200:
                sub_resp.encoding = 'windows-1254'
                sub_soup = BeautifulSoup(sub_resp.text, 'html.parser')
                sub_text = sub_soup.get_text(separator="\n")
                combined_text.append(f"--- TEBLİĞ METNİ ({sub_url}) ---\n" + sub_text)
        except Exception as e_sub:
            logger.debug(f"Alt sayfa indirme uyarısı [{sub_url}]: {e_sub}")

    if combined_text:
        return "\n\n".join(combined_text)

    return None


def run_gcp_bulk_extraction(
    start_year: int = 2020,
    end_year: int = 2026,
    limit_days: Optional[int] = None
) -> Dict[str, Any]:
    """
    2020 - 2026 yılları arasındaki Resmi Gazete kararlarını Vertex AI Gemini 2.5 Flash kullanarak harfi harfine Cloud SQL'e aktarır.
    """
    logger.info(f"=== GCP Vertex AI Resmi Gazete Bulk Extractor Başlatıldı ({start_year} - {end_year}) ===")
    logger.info(f"Kullanılan AI Modeli: {getattr(settings, 'DEFAULT_LLM_MODEL', 'gemini-2.5-flash')}")

    init_orm_tables()
    session = SessionLocal()

    total_days_processed = 0
    total_decisions_extracted = 0
    failed_days = 0

    start_date = datetime.date(start_year, 1, 1)
    today = datetime.date.today()
    end_date = min(datetime.date(end_year, 12, 31), today)

    current_date = start_date

    try:
        while current_date <= end_date:
            if limit_days and total_days_processed >= limit_days:
                logger.info(f"Gün sınırı ({limit_days}) ulaşıldı, işlem sonlandırılıyor.")
                break

            year = current_date.year
            month = current_date.month
            day = current_date.day
            pub_date_str = current_date.strftime("%Y-%m-%d")

            day_text = fetch_official_gazette_day_text(year, month, day)

            if day_text and len(day_text) > 100:
                try:
                    records = extract_and_save_official_gazette(
                        raw_text=day_text,
                        yayin_tarihi=pub_date_str,
                        resmi_gazete_sayisi=None,
                        kaynak_url=f"{RG_BASE}/eskiler/{year}/{month:02d}/{year}{month:02d}{day:02d}.htm",
                        db_session=session
                    )
                    if records:
                        total_decisions_extracted += len(records)
                        logger.info(f"  [GCP BİREBİR AKTARIM] {pub_date_str}: {len(records)} karar süzülüp Cloud SQL'e kaydedildi.")
                except Exception as e_proc:
                    logger.error(f"  [HATA] {pub_date_str} işleme hatası: {e_proc}")
                    failed_days += 1

            total_days_processed += 1
            current_date += datetime.timedelta(days=1)

        logger.info(f"=== GCP Bulk Extractor Tamamlandı ===")
        logger.info(f"Toplam İşlenen Gün: {total_days_processed}")
        logger.info(f"Toplam Süzülen Karar (Exact Match): {total_decisions_extracted}")

        return {
            "status": "SUCCESS",
            "start_year": start_year,
            "end_year": end_year,
            "days_processed": total_days_processed,
            "decisions_extracted": total_decisions_extracted,
            "failed_days": failed_days
        }

    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GCP Vertex AI Resmi Gazete 2020-2026 Bulk Extractor")
    parser.add_argument("--start-year", type=int, default=2020, help="Başlangıç Yılı (Örn: 2020)")
    parser.add_argument("--end-year", type=int, default=2026, help="Bitiş Yılı (Örn: 2026)")
    parser.add_argument("--limit-days", type=int, default=None, help="İşlenecek maksimum gün sayısı (Test için)")

    args = parser.parse_args()
    res = run_gcp_bulk_extraction(start_year=args.start_year, end_year=args.end_year, limit_days=args.limit_days)
    print(res)
