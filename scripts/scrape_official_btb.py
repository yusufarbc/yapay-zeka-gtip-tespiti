"""T.C. Ticaret Bakanlığı geçerli BTB kayıtlarını Cloud SQL'e idempotent aktarır."""

import argparse
import datetime
import logging
import os
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from api.db.database import GumrukEmsalKararModel, SessionLocal, init_orm_tables


logger = logging.getLogger("OfficialBTBSync")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BTB_LIST_URL = "https://uygulama.gtb.gov.tr/BTBBasvuru/Btbler"
GRID_ID = "ctl00_ContentPlaceHolder1_GridView1"
HEADERS = {
    "User-Agent": "GTIP-Mevzuat-Bot/3.0 (official-public-data; contact: system-admin)",
    "Accept-Language": "tr-TR,tr;q=0.9",
}


def _build_session() -> requests.Session:
    """Portalın geçici 429/5xx cevaplarını üstel gecikmeyle yeniden dener."""
    retry = Retry(
        total=6,
        connect=4,
        read=4,
        status=6,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _hidden_fields(soup: BeautifulSoup) -> Dict[str, str]:
    return {
        element.get("name"): element.get("value", "")
        for element in soup.select("input[type=hidden][name]")
    }


def _postback(
    session: requests.Session,
    soup: BeautifulSoup,
    event_target: str,
    event_argument: str = "",
) -> BeautifulSoup:
    payload = _hidden_fields(soup)
    payload["__EVENTTARGET"] = event_target
    payload["__EVENTARGUMENT"] = event_argument
    response = session.post(BTB_LIST_URL, data=payload, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _page_rows(soup: BeautifulSoup) -> List[Dict[str, str]]:
    grid = soup.select_one(f"#{GRID_ID}")
    if grid is None:
        return []

    rows: List[Dict[str, str]] = []
    for row in grid.select("tr"):
        cells = row.select("td")
        detail_link = row.select_one("a[href*='$btn']")
        if len(cells) < 4 or detail_link is None:
            continue
        href = detail_link.get("href", "")
        match = re.search(r"__doPostBack\('([^']+)'", href)
        if not match:
            continue
        rows.append({
            "event_target": match.group(1),
            "btb_no": cells[0].get_text(" ", strip=True),
            "gtip_code": cells[1].get_text(" ", strip=True),
            "product_description": cells[2].get_text(" ", strip=True),
            "issue_date": cells[3].get_text(" ", strip=True),
        })
    return rows


def _text_by_id(soup: BeautifulSoup, element_id: str) -> str:
    element = soup.select_one(f"#{element_id}")
    return element.get_text(" ", strip=True) if element else ""


def parse_btb_detail(soup: BeautifulSoup) -> Dict[str, str]:
    """Portal detay görünümünü saf ve test edilebilir bir sözlüğe dönüştürür."""
    return {
        "btb_no": _text_by_id(soup, "ctl00_ContentPlaceHolder1_lblBtbNo"),
        "gtip_code": _text_by_id(soup, "ctl00_ContentPlaceHolder1_lblGtip"),
        "issue_date": _text_by_id(soup, "ctl00_ContentPlaceHolder1_lblGbastar"),
        "legal_justification": _text_by_id(soup, "ctl00_ContentPlaceHolder1_lblSinger"),
        "product_description": _text_by_id(soup, "ctl00_ContentPlaceHolder1_lblEstanim"),
    }


def _parse_date(value: str) -> Optional[datetime.date]:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _reference_year(reference_no: Any) -> Optional[int]:
    """TR + bölge(6) + yıl(2) + sıra(4) biçimindeki BTB yılını çözer."""
    match = re.fullmatch(r"TR\d{6}(\d{2})\d{4}", str(reference_no or "").strip().upper())
    if not match:
        return None
    year = 2000 + int(match.group(1))
    return year if 2020 <= year <= datetime.date.today().year else None


def _format_gtip(value: str) -> str:
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) == 12:
        return f"{digits[:4]}.{digits[4:6]}.{digits[6:8]}.{digits[8:10]}.{digits[10:12]}"
    return value.strip()


def iter_official_btbs(
    max_pages: int = 1000,
    max_records: Optional[int] = None,
    existing_refs: Optional[set[str]] = None,
) -> Iterable[Dict[str, Any]]:
    """Yeni kayıttan eskiye ilerler ve tam altı yıllık tarih sınırında durur."""
    today = datetime.date.today()
    try:
        cutoff = today.replace(year=today.year - 6)
    except ValueError:
        cutoff = today.replace(year=today.year - 6, day=28)

    known_refs = existing_refs or set()
    session = _build_session()
    response = session.get(BTB_LIST_URL, headers=HEADERS, timeout=60)
    response.raise_for_status()
    page_soup = BeautifulSoup(response.text, "html.parser")
    seen: set[str] = set()
    yielded = 0

    for page_number in range(1, max_pages + 1):
        if page_number > 1:
            try:
                page_soup = _postback(
                    session,
                    page_soup,
                    GRID_ID.replace("_", "$"),
                    f"Page${page_number}",
                )
            except Exception:
                logger.exception("BTB sayfa %s tüm yeniden denemelere rağmen yüklenemedi", page_number)
                raise

        rows = _page_rows(page_soup)
        if not rows:
            break
        page_new = 0
        page_existing = 0

        for row in rows:
            if row["btb_no"] in seen:
                continue
            seen.add(row["btb_no"])
            issue_date = _parse_date(row["issue_date"])
            if issue_date and issue_date < cutoff:
                return

            # Önceki çalışmada kaydedilmiş kararlar için pahalı detay postback'ini
            # tekrarlama; sayfalar hızlıca geçilerek kaldığı yere ulaşılır.
            if row["btb_no"] in known_refs:
                page_existing += 1
                continue

            detail_soup = _postback(session, page_soup, row["event_target"])
            detail = parse_btb_detail(detail_soup)
            if not detail["btb_no"] or not detail["gtip_code"] or not detail["product_description"]:
                logger.warning("Eksik BTB detay kaydı atlandı: %s", row["btb_no"])
                continue

            parsed_date = _parse_date(detail["issue_date"]) or issue_date
            if parsed_date and issue_date and abs((parsed_date - issue_date).days) > 31:
                logger.warning(
                    "BTB %s detay/list tarihleri uyuşmuyor (%s / %s); liste tarihi kullanılıyor.",
                    detail["btb_no"], parsed_date, issue_date,
                )
                parsed_date = issue_date
            if parsed_date and parsed_date > datetime.date.today():
                inferred_year = _reference_year(detail["btb_no"])
                if inferred_year:
                    logger.warning(
                        "BTB %s gelecekte tarihli (%s); referans yılından %s olarak düzeltiliyor.",
                        detail["btb_no"], parsed_date, inferred_year,
                    )
                    parsed_date = parsed_date.replace(year=inferred_year)
            yield {
                "btb_no": detail["btb_no"],
                "gtip_code": _format_gtip(detail["gtip_code"]),
                "issue_date": parsed_date.isoformat() if parsed_date else detail["issue_date"],
                "product_description": detail["product_description"],
                "legal_justification": detail["legal_justification"],
                "source_url": BTB_LIST_URL,
            }
            yielded += 1
            page_new += 1
            if max_records and yielded >= max_records:
                return
            time.sleep(0.05)

        logger.info(
            "BTB sayfa %s işlendi; %s yeni detay, %s mevcut kayıt atlandı.",
            page_number,
            page_new,
            page_existing,
        )


def upsert_btbs(records: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    inserted = 0
    updated = 0
    with SessionLocal() as db:
        for item in records:
            record = db.query(GumrukEmsalKararModel).filter(
                GumrukEmsalKararModel.karar_tipi == "BTB",
                GumrukEmsalKararModel.referans_no == item["btb_no"],
            ).first()
            if record is None:
                record = GumrukEmsalKararModel(
                    karar_tipi="BTB",
                    referans_no=item["btb_no"],
                    gtip_kodu=item["gtip_code"],
                    chapter_code=re.sub(r"[^0-9]", "", item["gtip_code"])[:2],
                    yayin_tarihi=item["issue_date"],
                    esya_tanimi=item["product_description"],
                    hukuki_gerekce=item["legal_justification"],
                    kaynak_url=item["source_url"],
                    valid_until="9999-12-31",
                )
                db.add(record)
                inserted += 1
            else:
                record.gtip_kodu = item["gtip_code"]
                record.chapter_code = re.sub(r"[^0-9]", "", item["gtip_code"])[:2]
                record.yayin_tarihi = item["issue_date"]
                record.esya_tanimi = item["product_description"]
                record.hukuki_gerekce = item["legal_justification"]
                record.kaynak_url = item["source_url"]
                record.valid_until = "9999-12-31"
                updated += 1
            if (inserted + updated) % 25 == 0:
                db.commit()
        db.commit()
    return {"inserted": inserted, "updated": updated}


def run(max_pages: int = 1000, max_records: Optional[int] = None) -> Dict[str, int]:
    init_orm_tables()
    today = datetime.date.today()
    with SessionLocal() as db:
        existing_refs = {
            ref for ref, issue_date in db.query(
                GumrukEmsalKararModel.referans_no,
                GumrukEmsalKararModel.yayin_tarihi,
            ).filter(
                GumrukEmsalKararModel.karar_tipi == "BTB",
                GumrukEmsalKararModel.referans_no.isnot(None),
            )
            if ref and (_parse_date(str(issue_date or "")) or today) <= today
        }
    logger.info("Cloud SQL'de %s mevcut BTB referansı bulundu.", len(existing_refs))
    result = upsert_btbs(
        iter_official_btbs(
            max_pages=max_pages,
            max_records=max_records,
            existing_refs=existing_refs,
        )
    )
    logger.info("Resmî BTB senkronu tamamlandı: %s", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ticaret Bakanlığı resmî geçerli BTB senkronu")
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--max-records", type=int, default=None)
    args = parser.parse_args()
    run(max_pages=args.max_pages, max_records=args.max_records)
