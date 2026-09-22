"""
Uluslararası Gümrük Emsal Kararları Canlı Arama ve Analiz Motoru.

Avrupa Birliği (EBTI), Amerika Birleşik Devletleri (CBP CROSS / CustomsMobile)
ve Çin Halk Cumhuriyeti (GACC - 归类决定及裁定) resmi veritabanlarındaki
sınıflandırma kararlarını (Rulings) canlı araştırır, Dünya Gümrük Örgütü (WCO)
6 haneli HS uyumunu doğrular ve Türkçe hukuki gerekçe özeti üretir.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from api.config import settings
from api.schemas.product import InternationalRuling

logger = logging.getLogger("InternationalSearchEngine")

# Resmi Portal URL Şablonları
CUSTOMSMOBILE_SEARCH_URL = "https://www.customsmobile.com/rulings/search?q={query}"
CBP_RULINGS_HOME = "https://rulings.cbp.gov/home"
EBTI_CONSULTATION_URL = "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp?Lang=en"
CHINA_GACC_PORTAL_URL = "http://app.gjzwfw.gov.cn/jmopen/webapp/html5/gljdcdPC/index.html"


def generate_portal_links(query: str, hs_code: Optional[str] = None) -> Dict[str, str]:
    """Her üç resmi portal için doğrudan kullanıcıya sunulabilecek arama bağlantıları üretir."""
    clean_q = urllib.parse.quote(query.strip())
    clean_hs = urllib.parse.quote((hs_code or "").replace(".", "")[:6])
    search_term = f"{clean_hs}+{clean_q}" if clean_hs else clean_q

    return {
        "us_customsmobile": f"https://www.customsmobile.com/rulings/search?q={search_term}",
        "us_cbp_cross": "https://rulings.cbp.gov/home",
        "eu_ebti": f"https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp?Lang=en&Status=VALID&goodsDescription={clean_q}",
        "cn_gacc": CHINA_GACC_PORTAL_URL,
    }


def _clean_json_text(raw_text: str) -> str:
    """Markdown bloklarını (```json ... ```) temizleyip saf JSON metnini ayıklar."""
    if not raw_text:
        return "[]"
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def search_international_rulings(
    product_text: str,
    hs_code_hint: Optional[str] = None,
    target_countries: Optional[List[str]] = None,
    max_results: int = 4,
) -> List[InternationalRuling]:
    """
    ABD CBP CROSS (CustomsMobile), Çin GACC ve AB EBTI kararlarında
    Gemini Google Search Grounding kullanarak canlı emsal taraması yapar.
    """
    if not product_text or not product_text.strip():
        return []

    countries = target_countries or ["US", "CN", "EU"]

    # Test/Emülatör ortamında veya sağlayıcı erişimi yokken canlı arama yapılamaz.
    # Uydurma karar üretmek yerine boş dönülür; çağıran taraf kullanıcıya
    # generate_portal_links() ile resmi portal arama bağlantılarını sunar.
    if settings.USE_GCP_EMULATOR or not (settings.GEMINI_API_KEY or settings.GCP_PROJECT_ID):
        logger.info("[InternationalSearch] Canlı arama yapılamıyor; emsal listesi boş dönülüyor.")
        return []

    try:
        from api.modules.vertex_client import get_grounded_search_client
        from google.genai import types

        client = get_grounded_search_client()
        hs_context = f"Tahmini veya aday WCO HS Kodu: {hs_code_hint}" if hs_code_hint else ""

        prompt = f"""
Sen Dünya Gümrük Örgütü (WCO) ve uluslararası gümrük sınıflandırma uzmanısın.
Aşağıdaki ürün için resmi uluslararası gümrük kararları (Customs Rulings) veritabanlarında arama yap:

Ürün Tanımı: "{product_text}"
{hs_context}
Hedef Ülkeler / Veritabanları: {", ".join(countries)}

Özellikle şu resmi kaynakları ara:
1. ABD: CBP CROSS (Customs Rulings Online Search System) / customsmobile.com veya rulings.cbp.gov (NY veya HQ kararları)
2. Çin: Çin Gümrükler Genel İdaresi (GACC - 中国海关 商品归类决定及裁定 / gjzwfw.gov.cn veya customs.gov.cn)
3. AB: Avrupa Komisyonu DG TAXUD EBTI (Binding Tariff Information - ec.europa.eu)

Bulduğun en alakalı ve güncel emsal kararları analiz et. Her karar için aşağıdaki JSON şemasında çıktı ver:
[
  {{
    "country": "US | CN | EU",
    "ruling_no": "Karar Referans Numarası (örn: NY N320145, HQ H298123, Z2023-0012)",
    "hs_code": "Karardaki 6 haneli HS veya 8-10 haneli HTS/CN kodu",
    "product_description": "Karar metnindeki orijinal ürün açıklaması",
    "legal_justification": "Orijinal dildeki GİR (GRI 1-6) ve tarife notu gerekçesi",
    "summary_tr": "Kararın Türkçe hukuki analizi ve Türk GTİP sistemiyle uyumu",
    "issue_date": "YYYY-MM-DD biçiminde tarih veya null",
    "source_url": "Kararın resmi web sayfası bağlantısı (customsmobile.com, rulings.cbp.gov, ec.europa.eu veya gjzwfw.gov.cn)",
    "source_name": "ABD CBP CROSS (CustomsMobile) | Çin GACC (海关总署) | AB EBTI (TAXUD)",
    "similarity_score": 0.85
  }}
]

YALNIZCA geçerli bir JSON listesi döndür. Açıklama veya markdown formatı ekleme.
"""

        # Google Search Grounding ile canlı web taraması
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1,
        )

        response = client.models.generate_content(
            model=settings.REASONING_LLM_MODEL or "gemini-2.5-flash",
            contents=prompt,
            config=config,
        )

        raw_json = _clean_json_text(response.text or "")
        parsed_data = json.loads(raw_json)

        rulings: List[InternationalRuling] = []
        if isinstance(parsed_data, list):
            for item in parsed_data:
                try:
                    rulings.append(InternationalRuling(**item))
                except Exception as parse_err:
                    logger.debug("Karar parsing uyarısı: %s, veri: %s", parse_err, item)

        if rulings:
            logger.info(
                "[InternationalSearch] Gemini canlı aramasından %d uluslararası emsal bulundu.",
                len(rulings),
            )
            return rulings[:max_results]

        logger.warning("[InternationalSearch] Canlı arama boş sonuç döndü; emsal listesi boş dönülüyor.")
        return []

    except Exception as exc:
        # Uydurma emsal üretmek, kullanıcıya sahte hukuki dayanak sunmak demektir.
        # Arama başarısızsa karar uluslararası emsal olmadan tamamlanır.
        logger.warning(
            "[InternationalSearch] Canlı arama başarısız (%s); uluslararası emsal olmadan devam ediliyor.",
            exc,
        )
        return []


async def search_international_rulings_async(
    product_text: str,
    hs_code_hint: Optional[str] = None,
    target_countries: Optional[List[str]] = None,
    max_results: int = 4,
) -> List[InternationalRuling]:
    """Asenkron çalışma için search_international_rulings fonksiyonunu thread havuzunda yürütür."""
    import asyncio
    return await asyncio.to_thread(
        search_international_rulings,
        product_text=product_text,
        hs_code_hint=hs_code_hint,
        target_countries=target_countries,
        max_results=max_results,
    )
