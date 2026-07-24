import logging
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ResmiGazeteNotifier")

def send_google_chat_alert(title: str, pdf_url: str, webhook_url: str = None):
    message = (
        f"🚨 *YENİ GÜMRÜK MEVZUAT UYARISI* 🚨\n\n"
        f"Resmi Gazete'de yeni bir Gümrük Tarife/İthalat tebliği yayımlandı:\n"
        f"📌 *Başlık:* {title}\n"
        f"🔗 *Bağlantı:* {pdf_url}\n\n"
        f"Sistem yeni mevzuat versiyonlama boru hattını otomatik tetikledi."
    )
    
    if webhook_url:
        try:
            requests.post(webhook_url, json={"text": message})
        except Exception as e:
            logger.error(f"Google Chat webhook gönderimi başarısız: {e}")

    logger.info(f"Mevzuat Bildirimi Oluşturuldu: {title}")
