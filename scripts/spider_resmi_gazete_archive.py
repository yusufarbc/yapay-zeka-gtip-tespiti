import os
import sys
import datetime
import time
import logging
import requests
import urllib3
from bs4 import BeautifulSoup
from typing import List, Dict, Any

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

urllib3.disable_warnings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RGPDFSpider")

from scripts.parse_rg_pdf_digital import extract_gtip_records_from_digital_pdf, save_to_database_orm

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
RG_BASE = "https://www.resmigazete.gov.tr"

def scan_and_parse_day(year: int, month: int, day: int) -> int:
    """
    Belirtilen tarih için Resmî Gazete fihristini ve bağlantılı PDF eklerini tarar,
    içindeki GTİP sınıflandırma kararlarını veritabanına kaydeder.
    """
    date_str = f"{year}{month:02d}{day:02d}"
    pub_date = f"{year}-{month:02d}-{day:02d}"
    index_url = f"{RG_BASE}/eskiler/{year}/{month:02d}/{date_str}.htm"

    total_saved = 0
    try:
        resp = requests.get(index_url, headers=HEADERS, verify=False, timeout=8)
        if resp.status_code != 200:
            return 0

        # Encoding ayarla
        resp.encoding = 'windows-1254'
        soup = BeautifulSoup(resp.text, 'html.parser')

        pdf_urls_to_check = set()

        # 1. Doğrudan Fihristteki PDF linklerini bul
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            text = a.get_text(strip=True).lower()

            if href.endswith('.pdf'):
                # Gümrük, tarife, tebliğ, karar veya doğrudan günün ana pdf'i
                full_pdf_url = href if href.startswith('http') else f"{RG_BASE}/eskiler/{year}/{month:02d}/{href}"
                pdf_urls_to_check.add(full_pdf_url)

            # HTML Tebliğ sayfasına yönlendiriyorsa, o sayfanın içindeki PDF'leri de topla
            elif href.endswith('.htm') and href != f"{date_str}.htm":
                full_htm_url = href if href.startswith('http') else f"{RG_BASE}/eskiler/{year}/{month:02d}/{href}"
                # Filtre: İlgili olabilecek konular
                if any(k in text for k in ['gümrük', 'güm', 'tarife', 'sınıf', 'sinif', 'tebliğ', 'tebli', 'karar']):
                    try:
                        sub_resp = requests.get(full_htm_url, headers=HEADERS, verify=False, timeout=5)
                        if sub_resp.status_code == 200:
                            sub_resp.encoding = 'windows-1254'
                            sub_soup = BeautifulSoup(sub_resp.text, 'html.parser')
                            for sub_a in sub_soup.find_all('a', href=True):
                                sub_href = sub_a.get('href', '')
                                if sub_href.endswith('.pdf'):
                                    full_sub_pdf = sub_href if sub_href.startswith('http') else f"{RG_BASE}/eskiler/{year}/{month:02d}/{sub_href}"
                                    pdf_urls_to_check.add(full_sub_pdf)
                    except Exception:
                        pass

        # 2. Toplanan PDF'leri indir ve dijital PDF parser'dan geçir
        for pdf_url in pdf_urls_to_check:
            try:
                pdf_resp = requests.get(pdf_url, headers=HEADERS, verify=False, timeout=12)
                if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1000:
                    records = extract_gtip_records_from_digital_pdf(pdf_resp.content)
                    if records:
                        logger.info(f"  [BULUNDU] {pub_date} - {pdf_url}: {len(records)} kayıt çıkarıldı!")
                        saved = save_to_database_orm(records, pdf_url, pub_date)
                        total_saved += saved
            except Exception as e:
                logger.debug(f"PDF indirme/parse hatası [{pdf_url}]: {e}")

    except Exception as e:
        logger.debug(f"Gün tarama hatası [{pub_date}]: {e}")

    return total_saved

def run_spider_2020_to_2026():
    """
    2020 - 2026 yılları arasındaki tüm Resmî Gazete günlerini tarar.
    """
    logger.info("=== Dijital PDF GTİP / BTB Arşiv Taraması Başlatılıyor (2020 - 2026) ===")
    
    start_date = datetime.date(2020, 1, 1)
    end_date = datetime.date(2026, 8, 10)
    delta = datetime.timedelta(days=1)

    current_date = start_date
    grand_total = 0
    days_count = 0

    while current_date <= end_date:
        saved_today = scan_and_parse_day(current_date.year, current_date.month, current_date.day)
        grand_total += saved_today
        days_count += 1

        if days_count % 30 == 0:
            logger.info(f"İlerleme: {current_date.strftime('%Y-%m-%d')} taranıyor... Toplam eklenen kayıt: {grand_total}")

        current_date += delta
        time.sleep(0.02)

    logger.info(f"🎉 TARAMA TAMAMLANDI! Toplam {grand_total} yeni GTİP / BTB sınıflandırma kararı veritabanına eklendi.")

def run_spider_daily(days_back: int = 2) -> int:
    """
    Son X günü (bugün dahil) tarar. Cron job'lar için uygundur.
    """
    logger.info(f"=== Günlük Resmî Gazete Taraması Başlatılıyor (Son {days_back} Gün) ===")
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days_back)
    delta = datetime.timedelta(days=1)

    current_date = start_date
    grand_total = 0

    while current_date <= end_date:
        logger.info(f"Tarama Günü: {current_date.strftime('%Y-%m-%d')}")
        saved = scan_and_parse_day(current_date.year, current_date.month, current_date.day)
        grand_total += saved
        current_date += delta

    logger.info(f"Günlük tarama tamamlandı. {grand_total} yeni karar eklendi.")
    return grand_total

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--daily":
        run_spider_daily()
    else:
        run_spider_2020_to_2026()
