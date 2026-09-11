"""
Vertex AI Model Armor Güvenlik Duvarı (Prompt Injection & Sanitization Shield).
Kullanıcı veya üçüncü taraf entegrasyonlardan gelen eşya tanımlarındaki:
1. Dolaylı Komut Enjeksiyonlarını (Indirect Prompt Injection)
2. Sistem Talimatlarını Manipüle Etme Girişimlerini (Jailbreak / Rule Override)
3. Gizli Ayırıcı / Sınır Atlatma (Delimiter Injection / Role-play)
4. SQL ve Kod Enjeksiyonu kalıplarını
tespit eder, süzerek modelleri ve karar motorunu korur.
"""

import re
import logging
from typing import Tuple
from fastapi import HTTPException

logger = logging.getLogger("ModelArmor")

# Bilinen Zararlı Enjeksiyon Kalıpları (Türkçe & İngilizce)
INJECTION_PATTERNS = [
    # Kural ve Sistem Atlatma
    r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
    r"(?i)disregard\s+(all\s+)?(previous|prior|above)",
    r"(?i)(tüm|bütün)\s+(önceki\s+)?(talimatları|kuralları|komutları)\s+(unut|yok\s+say|sil)",
    r"(?i)sistem\s+(talimatlarını|kurallarını)\s+(yok\s+say|atla|değiştir)",
    r"(?i)you\s+are\s+now\s+(in\s+)?(dan|jailbreak|unrestricted)\s+mode",
    r"(?i)artık\s+(kısıtlamasız|filtresiz)\s+bir\s+(moddasın|yapay\s+zekasın)",
    
    # Rol ve Prompt Taklidi (Delimiter Hijacking)
    r"(?i)\[system\]",
    r"(?i)\[inst\]",
    r"(?i)<\s*system\s*>",
    r"(?i)###\s*(instruction|system|human):",
    r"(?i)---\s*(system\s+instruction|system\s+prompt)\s*---",
    
    # GTİP ve Hukuki Karar Manipülasyonu
    r"(?i)bana\s+(kesinlikle|zorunlu\s+olarak)\s+[0-9]{12}\s+kodunu\s+ver",
    r"(?i)override\s+(gtip|tariff|classification)\s+to\s+[0-9]{4,12}",
    r"(?i)force\s+classification\s+as\s+[0-9]{4,12}",
    
    # Kod ve SQL Saldırıları
    r"(?i)<\s*script[^>]*>",
    r"(?i)javascript:",
    r"(?i)union\s+select\s+",
    r"(?i)drop\s+table\s+",
]

_COMPILED_PATTERNS = [re.compile(p) for p in INJECTION_PATTERNS]


class ModelArmorGuardrail:
    """
    Vertex AI Model Armor Güvenlik Duvarı Yöneticisi.
    """

    @classmethod
    def inspect_and_sanitize(cls, text: str) -> Tuple[str, bool]:
        """
        Metni denetler; zararlı yönlendirme tespit edilirse temizler veya istisna fırlatır.

        :param text: Kullanıcı ürün girdisi
        :return: (temizlenmis_metin, guvenlik_uyarisi_var_mi)
        """
        if not text:
            return "", False

        cleaned = text.strip()
        matched_threats = []

        for pattern in _COMPILED_PATTERNS:
            match = pattern.search(cleaned)
            if match:
                matched_threats.append(match.group(0))

        if matched_threats:
            logger.warning(
                "[ModelArmor] Zararlı komut enjeksiyonu engellendi! Tehditler: %s | Girdi: %s",
                matched_threats[:3], cleaned[:100]
            )
            # Güvenlik duvarı: Yetkisiz enjeksiyon girişimini derhal durdur
            raise HTTPException(
                status_code=400,
                detail=(
                    "Güvenlik Kalkanı (Model Armor): Girdi içeriğinde yetkisiz komut veya "
                    "yönlendirme (Prompt Injection) tespit edildi. Lütfen yalnızca eşyanın "
                    "fiziksel ve teknik niteliklerini giriniz."
                )
            )

        # Kontrol karakterlerini temizle (Null byte, görünmeyen Unicode kontrol karakterleri)
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
        return sanitized, False


model_armor = ModelArmorGuardrail()
