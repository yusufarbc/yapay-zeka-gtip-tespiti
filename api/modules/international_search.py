"""
Uluslararası gümrük portallarına doğrudan arama bağlantıları üretir.

NEDEN CANLI ARAMA YOK
---------------------
Bu modülde daha önce Gemini Google Search Grounding ile ABD CBP CROSS, AB EBTI
ve Çin GACC kararlarını canlı arayan bir işlev vardı. Ölçüm kaldırılmasını
gerektirdi:

  - Üretimde her çağrı 504 DEADLINE_EXCEEDED ile bitiyordu; ~25 saniye harcanıp
    sıfır sonuç dönüyordu.
  - Timeout 15, 20 ve 45 saniye denendi; hiçbiri yetmedi.
  - Prompt yalınlaştırılıp yalnız dört alan istendiğinde bile çağrı 63 saniye
    sürdü. Yani gecikme prompt boyutundan değil, grounding'in kendisinden
    geliyor ve senkron bir istek bütçesine sığmıyor.
  - Sonuçlar sınıflandırmaya etki etmiyordu: arama karar kilitlendikten sonra
    çalışıyor ve çıktısı yalnız gösterime giriyordu.

Geriye kalan, kullanıcının araştırmayı kendisi sürdürmesini sağlayan resmî
portal bağlantılarıdır: model çağrısı yoktur, maliyeti yoktur, her zaman çalışır.
"""

from __future__ import annotations

import urllib.parse
from typing import Dict, Optional

# Resmî portal URL şablonları
CBP_RULINGS_HOME = "https://rulings.cbp.gov/home"
EBTI_CONSULTATION_URL = "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp?Lang=en"
CHINA_GACC_PORTAL_URL = "http://app.gjzwfw.gov.cn/jmopen/webapp/html5/gljdcdPC/index.html"


def generate_portal_links(query: str, hs_code: Optional[str] = None) -> Dict[str, str]:
    """Üç resmî portal için doğrudan açılabilir arama bağlantıları üretir."""
    clean_q = urllib.parse.quote(str(query or "").strip())
    clean_hs = urllib.parse.quote(str(hs_code or "").replace(".", "")[:6])
    search_term = f"{clean_hs}+{clean_q}" if clean_hs else clean_q

    return {
        "us_customsmobile": f"https://www.customsmobile.com/rulings/search?q={search_term}",
        "us_cbp_cross": CBP_RULINGS_HOME,
        "eu_ebti": (
            "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp"
            f"?Lang=en&Status=VALID&goodsDescription={clean_q}"
        ),
        "cn_gacc": CHINA_GACC_PORTAL_URL,
    }
