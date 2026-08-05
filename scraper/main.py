import os
import sys
import logging
from scraper.keyword_checker import check_text_for_triggers
from scraper.notifier import send_google_chat_alert

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from scripts.sync_customs_data import scrape_resmi_gazete_rss, scrape_ticaret_bakanligi_btb_portal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ResmiGazeteScraper")

def run_daily_scraper():
    logger.info("Resmi Gazete ve Ticaret Bakanlığı canlı mevzuat kontrolü başlatılıyor (02:00 Cron Job)...")

    # Canlı RSS / Web Akışını Çek
    resmi_gazete_articles = scrape_resmi_gazete_rss()
    btb_decisions = scrape_ticaret_bakanligi_btb_portal()

    for article in resmi_gazete_articles:
        title = article.get("title", "")
        url = article.get("link", "https://www.resmigazete.gov.tr")

        if check_text_for_triggers(title):
            logger.warning(f"GÜMRÜK TARİFE TEBLİĞİ TESPİT EDİLDİ: {title}")
            send_google_chat_alert(title=title, pdf_url=url)
        else:
            logger.info(f"İlgisiz başlık atlandı: {title[:40]}...")

    if btb_decisions:
        logger.info(f"[LIVE SCRAPER] Ticaret Bakanlığı portalından {len(btb_decisions)} adet yeni BTB kararı senkronize edildi.")

if __name__ == "__main__":
    run_daily_scraper()

