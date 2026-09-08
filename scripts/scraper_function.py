"""Resmî Gazete gümrük mevzuatı HTML ayrıştırma ve Cloud SQL yükleme hattı."""

import logging
import re
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("OfficialGazetteETL")

CUSTOMS_KEYWORDS = (
    "gümrük",
    "ithalat",
    "ihracat",
    "tarife",
    "gtip",
    "g.t.i.p",
    "menşe",
    "antrepo",
    "dış ticaret",
    "serbest bölge",
    "damping",
    "korunma önlemi",
    "gözetim uygulanması",
)

ARTICLE_PATTERN = re.compile(
    r"(?im)^\s*((?:GEÇİCİ\s+|EK\s+)?MADDE\s+\d+(?:/[A-ZÇĞİÖŞÜ0-9]+)?)\s*[-–—]?\s*"
)
LAW_NUMBER_PATTERN = re.compile(r"(\d{3,5})\s+sayılı\s+[^\n]{0,120}?(?:Kanun|Kararname)", re.IGNORECASE)


def clean_html(raw_html: str) -> str:
    """HTML etiketlerini ve Office/Word artıklarını temizler."""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["o:p", "style", "script", "meta", "link", "noscript"]):
        tag.decompose()
    for span in soup.find_all("span"):
        span.unwrap()
    return soup.get_text(separator="\n", strip=True)


def is_customs_related(text_value: str) -> bool:
    normalized = (text_value or "").casefold()
    return any(keyword.casefold() in normalized for keyword in CUSTOMS_KEYWORDS)


def extract_customs_articles(raw_html: str) -> List[Dict[str, str]]:
    """Gümrükle ilgili bir RG HTML belgesini atomik MADDE parçalarına ayırır."""
    cleaned_text = clean_html(raw_html)
    if not is_customs_related(cleaned_text):
        return []

    matches = list(ARTICLE_PATTERN.finditer(cleaned_text))
    if not matches:
        return []

    header_text = cleaned_text[: matches[0].start()]
    title_lines = [line.strip() for line in header_text.splitlines() if line.strip()]
    title = title_lines[-1][:500] if title_lines else "Doğrudan Düzenleme"
    header_law_match = LAW_NUMBER_PATTERN.search(header_text)
    current_law_no = header_law_match.group(1) if header_law_match else title

    articles: List[Dict[str, str]] = []
    for index, match in enumerate(matches):
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned_text)
        article_text = cleaned_text[match.end():content_end].strip()
        if len(article_text) < 20:
            continue

        law_match = LAW_NUMBER_PATTERN.search(article_text)
        if law_match:
            current_law_no = law_match.group(1)

        articles.append({
            "kanun_no": str(current_law_no)[:50],
            "madde_kodu": match.group(1).strip().upper()[:100],
            "madde_metni": article_text[:15000],
            "baslik": title,
        })
    return articles


def _gazette_number_as_int(gazette_no: Any) -> int:
    match = re.search(r"\d+", str(gazette_no or ""))
    return int(match.group(0)) if match else 0


def ingest_gazette_document(
    raw_html: str,
    source_url: str,
    pub_date: str,
    gazette_no: Any,
    skip_embedding: bool = False,
) -> Dict[str, Any]:
    """Tek bir ilgili mevzuat HTML belgesini idempotent olarak Cloud SQL'e yazar."""
    # Saf HTML ayrıştırıcının test/import sırasında GCP SDK ve DB bağlantılarını
    # yüklememesi için ağır bağımlılıklar yalnızca gerçek ingest anında alınır.
    from api.db.database import GumrukMevzuatMaddesiModel, SessionLocal
    from api.modules.vertex_client import generate_embedding

    articles = extract_customs_articles(raw_html)
    if not articles:
        return {"status": "SKIPPED", "inserted_articles": 0, "updated_articles": 0}

    inserted = 0
    updated = 0
    gazette_number = _gazette_number_as_int(gazette_no)

    with SessionLocal() as session:
        for article in articles:
            vector = None
            if not skip_embedding:
                try:
                    chunk_text = (
                        f"{article['kanun_no']} {article['madde_kodu']}: "
                        f"{article['madde_metni'][:1500]}"
                    )
                    generated = generate_embedding(chunk_text)
                    vector = generated if generated and any(generated) else None
                except Exception as exc:
                    logger.warning("Mevzuat embedding üretilemedi (%s): %s", source_url, exc)

            existing = session.query(GumrukMevzuatMaddesiModel).filter(
                GumrukMevzuatMaddesiModel.tarih == pub_date,
                GumrukMevzuatMaddesiModel.madde_kodu == article["madde_kodu"],
                GumrukMevzuatMaddesiModel.kaynak_url == source_url,
            ).first()

            if existing:
                existing.resmi_gazete_sayisi = gazette_number
                existing.kanun_no = article["kanun_no"]
                existing.madde_metni = article["madde_metni"]
                if vector is not None:
                    existing.icerik_vektor = vector
                updated += 1
            else:
                session.add(GumrukMevzuatMaddesiModel(
                    tarih=pub_date,
                    resmi_gazete_sayisi=gazette_number,
                    kanun_no=article["kanun_no"],
                    madde_kodu=article["madde_kodu"],
                    madde_metni=article["madde_metni"],
                    kaynak_url=source_url,
                    icerik_vektor=vector,
                ))
                inserted += 1

        session.commit()

    logger.info(
        "[Resmî Gazete ETL] %s: %s yeni, %s güncel madde (%s)",
        pub_date,
        inserted,
        updated,
        source_url,
    )
    return {"status": "SUCCESS", "inserted_articles": inserted, "updated_articles": updated}


def ingest_daily_gazette(date_str: str, gazette_no: int = 1, skip_embedding: bool = False) -> Dict[str, Any]:
    """Geriye uyumlu giriş: günlük fihristteki ilgili HTML belgelerini tarar."""
    index_url = f"https://www.resmigazete.gov.tr/eskiler/{date_str[:4]}/{date_str[4:6]}/{date_str}.htm"
    try:
        response = requests.get(index_url, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        return {"status": "FAILED", "reason": f"Ağ hatası: {exc}"}

    response.encoding = "windows-1254"
    soup = BeautifulSoup(response.text, "html.parser")
    pub_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    total_inserted = 0
    total_updated = 0

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        context = anchor.parent.get_text(" ", strip=True) if anchor.parent else anchor.get_text(" ", strip=True)
        if not href.lower().endswith((".htm", ".html")) or not is_customs_related(context):
            continue

        document_url = urljoin(index_url, href)
        try:
            document_response = requests.get(document_url, timeout=30)
            document_response.raise_for_status()
            document_response.encoding = "windows-1254"
            result = ingest_gazette_document(
                document_response.text,
                document_url,
                pub_date,
                gazette_no,
                skip_embedding=skip_embedding,
            )
            total_inserted += result.get("inserted_articles", 0)
            total_updated += result.get("updated_articles", 0)
        except Exception as exc:
            logger.warning("Resmî Gazete belgesi işlenemedi (%s): %s", document_url, exc)

    return {
        "status": "SUCCESS",
        "inserted_articles": total_inserted,
        "updated_articles": total_updated,
    }


def main_cloud_function(request):
    """Eski Cloud Function giriş noktası; yeni kurulum Cloud Run Job kullanır."""
    import datetime

    today_str = datetime.datetime.now().strftime("%Y%m%d")
    return ingest_daily_gazette(today_str)
