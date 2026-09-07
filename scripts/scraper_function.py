"""
Resmi Gazete Günlük Mevzuat Radarı (Cloud Run Function 2nd Gen).
gcp_architecture_report.md Bölüm 3 Şartnamesi.
Her gece saat 02:00'de Cloud Scheduler tarafından tetiklenir.
Resmi Gazete HTML sayfasını temizler, gümrük maddelerini atomik olarak ayrıştırır,
Vertex AI text-embedding-005 ile vektörleştirir ve AlloyDB / Cloud SQL'e yazar.
"""

import os
import re
import logging
import requests
import urllib3
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from api.modules.vertex_client import generate_embedding
from api.db.database import SessionLocal, GumrukMevzuatMaddesiModel

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("OfficialGazetteETL")

CUSTOMS_KEYWORDS = [
    "gümrük", "ithalat", "ihracat", "tarife", "damping", 
    "menşe", "kaçakçılık", "dış ticaret", "kambiyo", "antrepo", 
    "katma değer vergisi", "özel tüketim vergisi", "vergi usul"
]

def clean_html(raw_html: str) -> str:
    """HTML etiketlerini ve Office/Word artıklarını temizler."""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["o:p", "style", "script", "meta", "link"]):
        tag.decompose()
    for span in soup.find_all("span"):
        span.unwrap()
    return soup.get_text(separator="\n", strip=True)

def ingest_daily_gazette(date_str: str, gazette_no: int = 1) -> Dict[str, Any]:
    """
    Belirtilen günün Resmi Gazete sayfasını çeker ve gümrük maddelerini veritabanına kaydeder.
    date_str formatı: YYYYMMDD (Örn: '20260907')
    """
    base_url = f"https://www.resmigazete.gov.tr/eskiler/{date_str[:4]}/{date_str[4:6]}/{date_str}-{gazette_no}.htm"
    try:
        response = requests.get(base_url, timeout=30, verify=False)
    except Exception as e:
        return {"status": "FAILED", "reason": f"Ağ hatası: {str(e)}"}

    if response.status_code != 200:
        return {"status": "SKIPPED", "reason": f"Resmi Gazete sayfası bulunamadı ({response.status_code})"}

    response.encoding = "windows-1254"
    cleaned_text = clean_html(response.text)

    # 1. Aşama: Gümrük ve Dış Ticaret İlgililik Kontrolü
    if not any(kw in cleaned_text.lower() for kw in CUSTOMS_KEYWORDS):
        return {"status": "SKIPPED", "reason": "Gümrük veya dış ticaret ile ilgili içerik bulunamadı."}

    # 2. Aşama: Madde Ayrıştırma (Regex Engine)
    pattern = re.compile(
        r"((?:GEÇİCİ\s+MADDE|EK\s+MADDE|MADDE)\s+\d+[\w\/\s\-]*)", 
        re.IGNORECASE
    )
    tokens = pattern.split(cleaned_text)
    
    current_law_no = "Doğrudan Düzenleme"
    articles_to_insert = []
    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    with SessionLocal() as session:
        for i in range(1, len(tokens), 2):
            madde_baslik = tokens[i].strip()
            madde_icerik = tokens[i+1].strip() if i+1 < len(tokens) else ""

            # Atıf yapılan kanun numarasını yakala (Örn: 3065, 4458)
            law_match = re.search(r"(\d{3,5})\s+sayılı\s+([A-Za-zÇĞİÖŞÜçğıöşü\s]+Kanun)", madde_icerik)
            if law_match:
                current_law_no = law_match.group(1)

            # Vektör üret
            chunk_text = f"{current_law_no} Sayılı Kanun {madde_baslik}: {madde_icerik[:1000]}"
            vector = generate_embedding(chunk_text)

            record = GumrukMevzuatMaddesiModel(
                tarih=formatted_date,
                resmi_gazete_sayisi=gazette_no,
                kanun_no=current_law_no,
                madde_kodu=madde_baslik,
                madde_metni=madde_icerik[:15000],
                kaynak_url=base_url,
                icerik_vektor=vector if any(vector) else None
            )
            session.add(record)
            articles_to_insert.append(madde_baslik)

        session.commit()

    logger.info(f"[Resmi Gazete ETL] {formatted_date} için {len(articles_to_insert)} madde başarıyla yüklendi.")
    return {"status": "SUCCESS", "inserted_articles": len(articles_to_insert)}

def main_cloud_function(request):
    """Cloud Run Function HTTP veya Pub/Sub giriş noktası."""
    import datetime
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    result = ingest_daily_gazette(today_str)
    return result
