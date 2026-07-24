import logging
from scraper.keyword_checker import check_text_for_triggers
from scraper.notifier import send_google_chat_alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ResmiGazeteScraper")

def run_daily_scraper():
    logger.info("Resmi Gazete günlük mevzuat kontrolü başlatılıyor (02:00 Cron Job)...")

    # Simulation of checking resmigazete.gov.tr feed
    mock_today_articles = [
        {
            "title": "İthalat Rejimi Kararında Değişiklik Yapılmasına Dair Cumhurbaşkanı Kararı (Karar Sayısı: 9812)",
            "url": "https://www.resmigazete.gov.tr/eskiler/2026/07/20260724-1.pdf"
        },
        {
            "title": "Çevre Hizmetleri Hakkında Yönetmelikte Değişiklik",
            "url": "https://www.resmigazete.gov.tr/eskiler/2026/07/20260724-2.pdf"
        }
    ]

    for article in mock_today_articles:
        title = article["title"]
        url = article["url"]

        if check_text_for_triggers(title):
            logger.warning(f"GÜMRÜK TARİFE TEBLİĞİ TESPİT EDİLDİ: {title}")
            send_google_chat_alert(title=title, pdf_url=url)
        else:
            logger.info(f"İlgisiz başlık atlandı: {title[:40]}...")

if __name__ == "__main__":
    run_daily_scraper()
