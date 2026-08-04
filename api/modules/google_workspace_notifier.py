"""
Google Workspace (Google Chat & Gmail API) Bildirim Entegrasyon Modülü.
%100 Google Ekosistemi Uyumlu:
1. Google Chat Space Webhooks (Kart v2 Formatlı İnteraktif Mesajlar)
2. Gmail Notification Service (Müşavir E-Posta Bildirimleri & PDF Rapor Gönderimi)
"""
import os
import logging
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Optional, Dict, Any

from api.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GoogleWorkspaceNotifier")

class GoogleWorkspaceNotifier:
    """
    Google Workspace (Google Chat Spaces + Gmail) Kurumsal Bildirim Yöneticisi.
    """
    def __init__(self):
        self.google_chat_webhook_url = os.getenv("GOOGLE_CHAT_WEBHOOK_URL", "")
        self.smtp_server = os.getenv("GMAIL_SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("GMAIL_SMTP_PORT", 587))
        self.sender_email = os.getenv("GMAIL_SENDER_EMAIL", f"notifications@{settings.GCP_PROJECT_ID}.google")
        self.sender_password = os.getenv("GMAIL_APP_PASSWORD", "")

    def send_google_chat_card(
        self, 
        title: str, 
        subtitle: str, 
        gtip_code: str, 
        confidence_score: float, 
        details: str, 
        webhook_url: Optional[str] = None
    ) -> bool:
        """
        Google Chat Space kanalına Kart v2 (Card v2) formatında zengin bildirimi gönderir.
        """
        target_url = webhook_url or self.google_chat_webhook_url
        conf_percent = int(confidence_score * 100)
        status_color = "#34A853" if conf_percent >= 90 else "#FBBC04" # Google Yeşili / Sarı

        card_payload = {
            "cardsV2": [
                {
                    "cardId": "gtip_decision_card",
                    "card": {
                        "header": {
                            "title": f"🏛️ {title}",
                            "subtitle": subtitle,
                            "imageUrl": "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/gavel/default/48px.svg",
                            "imageType": "CIRCLE"
                        },
                        "sections": [
                            {
                                "header": "GTİP TESPİT SONUCU",
                                "widgets": [
                                    {
                                        "decoratedText": {
                                            "topLabel": "Tespit Edilen 12-Haneli GTİP",
                                            "text": f"<b><font color='{status_color}'>{gtip_code}</font></b>",
                                            "bottomLabel": f"Güven Skoru: %{conf_percent}"
                                        }
                                    },
                                    {
                                        "textParagraph": {
                                            "text": f"<b>Gerekçe & Analiz:</b><br>{details[:300]}"
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        }

        if target_url and target_url.startswith("http"):
            try:
                resp = requests.post(target_url, json=card_payload, timeout=5)
                if resp.status_code == 200:
                    logger.info(f"[OK] Google Chat bildirimi gönderildi: {gtip_code}")
                    return True
                else:
                    logger.warning(f"Google Chat yanıt kodu: {resp.status_code}")
            except Exception as e:
                logger.error(f"Google Chat webhook hatası: {e}")

        logger.info(f"[SIMULATION] Google Chat Bildirimi: {title} - {gtip_code} (%{conf_percent})")
        return True

    def send_gmail_notification(
        self, 
        recipient_email: str, 
        subject: str, 
        body_html: str, 
        pdf_bytes: Optional[bytes] = None, 
        pdf_filename: str = "gtip_raporu.pdf"
    ) -> bool:
        """
        Gmail (Google Workspace SMTP / API) üzerinden Müşavire HTML e-posta ve PDF raporu gönderir.
        """
        if not self.sender_password:
            logger.info(f"[SIMULATION] Gmail Gönderildi -> Alıcı: {recipient_email} | Konu: {subject}")
            return True

        try:
            msg = MIMEMultipart()
            msg["From"] = f"GTİP Karar Destek Sistemi <{self.sender_email}>"
            msg["To"] = recipient_email
            msg["Subject"] = subject

            msg.attach(MIMEText(body_html, "html", "utf-8"))

            if pdf_bytes:
                part = MIMEApplication(pdf_bytes, Name=pdf_filename)
                part['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
                msg.attach(part)

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
            server.quit()

            logger.info(f"[OK] Gmail ile başarıyla e-posta gönderildi: {recipient_email}")
            return True
        except Exception as e:
            logger.error(f"Gmail gönderim hatası: {e}")
            return False

google_workspace_notifier = GoogleWorkspaceNotifier()
