"""Ticaret Bakanlığı BTB portalını aylık pencerelerle eksiksiz senkronize eder.

Portal ASP.NET WebForms durum alanlarını kullandığı için her aylık pencere kendi
oturumunda başlatılır; sayfalar boş sonuç dönene kadar ilerletilir. Kayıt anahtarı
uygulama şemasındaki (karar_tipi='BTB', referans_no=btb_no) çiftidir.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from api.db.database import GumrukEmsalKararModel, SessionLocal, init_orm_tables


logger = logging.getLogger("BulkBTBScraper")
BTB_LIST_URL = os.getenv("BTB_LIST_URL", "https://uygulama.gtb.gov.tr/BTBBasvuru/Btbler")
GRID_ID = "ctl00_ContentPlaceHolder1_GridView1"
HEADERS = {
    "User-Agent": "GTIP-Mevzuat-Sync/4.0 (official-public-data)",
    "Accept-Language": "tr-TR,tr;q=0.9",
}


@dataclass(frozen=True)
class MonthWindow:
    start: dt.date
    end: dt.date


def iter_month_windows(start: dt.date, end: dt.date) -> Iterator[MonthWindow]:
    """Kapalı tarih aralığını çakışmayan takvim aylarına böler."""
    if start > end:
        raise ValueError("Başlangıç tarihi bitiş tarihinden sonra olamaz.")
    cursor = start.replace(day=1)
    while cursor <= end:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        window_start = max(start, cursor)
        window_end = min(end, cursor.replace(day=last_day))
        yield MonthWindow(window_start, window_end)
        cursor = (cursor.replace(day=28) + dt.timedelta(days=4)).replace(day=1)


def build_http_session() -> requests.Session:
    retry = Retry(
        total=7, connect=5, read=5, status=7, backoff_factor=1.2,
        status_forcelist=(408, 429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True, raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2)
    session = requests.Session()
    session.headers.update(HEADERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _hidden_fields(soup: BeautifulSoup) -> Dict[str, str]:
    return {
        node.get("name"): node.get("value", "")
        for node in soup.select("input[type=hidden][name]")
        if node.get("name")
    }


def _find_control(soup: BeautifulSoup, patterns: Tuple[str, ...], tag: str = "input") -> Optional[str]:
    for node in soup.find_all(tag):
        identity = f"{node.get('id', '')} {node.get('name', '')}".lower()
        if all(any(token in identity for token in group.split("|")) for group in patterns):
            return node.get("name") or node.get("id")
    return None


def _search_payload(soup: BeautifulSoup, window: MonthWindow) -> Dict[str, str]:
    payload = _hidden_fields(soup)
    start_name = _find_control(soup, ("bas|baş|start|ilk", "tar|tarih|date"))
    end_name = _find_control(soup, ("bit|son|end", "tar|tarih|date"))
    if not start_name or not end_name:
        date_inputs = [
            node.get("name") for node in soup.select("input[name]")
            if any(word in f"{node.get('id', '')} {node.get('name', '')}".lower() for word in ("tarih", "date"))
        ]
        if len(date_inputs) >= 2:
            start_name, end_name = date_inputs[:2]
    if not start_name or not end_name:
        raise RuntimeError("Portal tarih filtre alanları bulunamadı; HTML sözleşmesi değişmiş olabilir.")
    payload[start_name] = window.start.strftime("%d/%m/%Y")
    payload[end_name] = window.end.strftime("%d/%m/%Y")

    for select in soup.select("select[name]"):
        identity = f"{select.get('id', '')} {select.get('name', '')}".lower()
        if any(word in identity for word in ("pagesize", "sayfasay", "kayitsay", "kayıtsay")):
            values = [option.get("value") for option in select.select("option[value]")]
            payload[select.get("name")] = "50" if "50" in values else values[-1]

    button = next((
        node for node in soup.select("input[type=submit][name],button[name]")
        if any(word in f"{node.get('id', '')} {node.get('name', '')} {node.get('value', '')}".lower()
               for word in ("ara", "sorgula", "listele", "search"))
    ), None)
    if button:
        payload[button.get("name")] = button.get("value", "Ara")
    return payload


def _post(session: requests.Session, payload: Dict[str, str]) -> BeautifulSoup:
    response = session.post(BTB_LIST_URL, data=payload, timeout=(15, 90))
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _rows(soup: BeautifulSoup) -> List[Dict[str, str]]:
    grid = soup.select_one(f"#{GRID_ID}") or soup.find("table", id=re.compile("grid", re.I))
    if grid is None:
        return []
    result: List[Dict[str, str]] = []
    for row in grid.select("tr"):
        cells = row.select("td")
        if len(cells) < 4:
            continue
        link = row.find("a", href=True)
        href = link.get("href", "") if link else ""
        postback = re.search(r"__doPostBack\('([^']+)'(?:,'([^']*)')?", href)
        result.append({
            "btb_no": cells[0].get_text(" ", strip=True),
            "gtip_code": cells[1].get_text(" ", strip=True),
            "product_description": cells[2].get_text(" ", strip=True),
            "issue_date": cells[3].get_text(" ", strip=True),
            "event_target": postback.group(1) if postback else "",
            "event_argument": postback.group(2) if postback and postback.group(2) else "",
            "detail_url": requests.compat.urljoin(BTB_LIST_URL, href) if href and not postback else "",
        })
    return [item for item in result if item["btb_no"]]


def _labeled_text(soup: BeautifulSoup, label_words: Tuple[str, ...], known_ids: Tuple[str, ...]) -> str:
    for element_id in known_ids:
        node = soup.select_one(f"#{element_id}")
        if node:
            return node.get_text(" ", strip=True)
    for cell in soup.select("th,td,dt,label"):
        label = cell.get_text(" ", strip=True).lower()
        if any(word in label for word in label_words):
            sibling = cell.find_next_sibling(["td", "dd"])
            if sibling:
                return sibling.get_text(" ", strip=True)
    return ""


def parse_detail(soup: BeautifulSoup, fallback: Dict[str, str]) -> Dict[str, str]:
    """Detay popup'ındaki tam eşya tanımı ve yasal gerekçeyi çıkarır."""
    return {
        "btb_no": _labeled_text(soup, ("btb no", "referans"), ("ctl00_ContentPlaceHolder1_lblBtbNo",)) or fallback["btb_no"],
        "gtip_code": _labeled_text(soup, ("gtip", "tarife"), ("ctl00_ContentPlaceHolder1_lblGtip",)) or fallback["gtip_code"],
        "issue_date": _labeled_text(soup, ("başlangıç", "tarih"), ("ctl00_ContentPlaceHolder1_lblGbastar",)) or fallback["issue_date"],
        "product_description": _labeled_text(soup, ("eşya tan", "ürün tan"), ("ctl00_ContentPlaceHolder1_lblEstanim",)) or fallback["product_description"],
        "legal_justification": _labeled_text(soup, ("gerekçe", "sınıflandırma gerek"), ("ctl00_ContentPlaceHolder1_lblSinger",)),
        "source_url": fallback.get("detail_url") or BTB_LIST_URL,
    }


def _detail_soup(session: requests.Session, page_soup: BeautifulSoup, row: Dict[str, str]) -> BeautifulSoup:
    if row.get("detail_url"):
        response = session.get(row["detail_url"], timeout=(15, 90))
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    payload = _hidden_fields(page_soup)
    payload.update({"__EVENTTARGET": row["event_target"], "__EVENTARGUMENT": row["event_argument"]})
    return _post(session, payload)


def scrape_month(session: requests.Session, window: MonthWindow, delay: float = 0.2) -> Iterator[Dict[str, str]]:
    response = session.get(BTB_LIST_URL, timeout=(15, 90))
    response.raise_for_status()
    initial = BeautifulSoup(response.text, "html.parser")
    page_soup = _post(session, _search_payload(initial, window))
    page = 1
    seen: set[str] = set()
    while True:
        rows = _rows(page_soup)
        new_rows = [row for row in rows if row["btb_no"] not in seen]
        if not new_rows:
            break
        for row in new_rows:
            seen.add(row["btb_no"])
            try:
                detail = parse_detail(_detail_soup(session, page_soup, row), row)
                if detail["gtip_code"] and detail["product_description"]:
                    yield detail
                else:
                    logger.warning("Eksik BTB kaydı atlandı: %s", row["btb_no"])
            except requests.RequestException:
                logger.exception("BTB detay sayfası alınamadı: %s", row["btb_no"])
            time.sleep(max(0.0, delay) + random.uniform(0.0, 0.15))

        page += 1
        payload = _hidden_fields(page_soup)
        payload.update({
            "__EVENTTARGET": GRID_ID.replace("_", "$"),
            "__EVENTARGUMENT": f"Page${page}",
        })
        page_soup = _post(session, payload)


def _normalize_gtip(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) in {6, 8, 10, 12} else str(value or "").strip()


def upsert_batch(records: Iterable[Dict[str, str]]) -> Dict[str, int]:
    materialized = list({item["btb_no"]: item for item in records}.values())
    if not materialized:
        return {"inserted": 0, "updated": 0}
    with SessionLocal() as db:
        references = [item["btb_no"] for item in materialized]
        existing_refs = {
            value for (value,) in db.query(GumrukEmsalKararModel.referans_no).filter(
                GumrukEmsalKararModel.karar_tipi == "BTB",
                GumrukEmsalKararModel.referans_no.in_(references),
            ).all()
        }
        inserted = len(set(references) - existing_refs)
        updated = len(set(references) & existing_refs)
        rows = []
        for item in materialized:
            normalized_gtip = _normalize_gtip(item["gtip_code"])
            rows.append({
                "karar_tipi": "BTB",
                "referans_no": item["btb_no"],
                "gtip_kodu": normalized_gtip,
                "chapter_code": normalized_gtip[:2],
                "yayin_tarihi": item["issue_date"],
                "esya_tanimi": item["product_description"],
                "hukuki_gerekce": item.get("legal_justification") or "",
                "kaynak_url": item.get("source_url") or BTB_LIST_URL,
                "valid_until": "9999-12-31",
            })

        # Yeni şemalarda tek SQL ON CONFLICT işlemi kullanılır. Eski kurulumda
        # unique indeks henüz yoksa veri kaybetmeden ORM uyumluluk yoluna düşülür.
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        unique_sets = {
            tuple(item.get("column_names") or [])
            for item in inspector.get_unique_constraints(GumrukEmsalKararModel.__tablename__)
        }
        supports_conflict = ("karar_tipi", "referans_no") in unique_sets
        if supports_conflict and db.bind.dialect.name in {"postgresql", "sqlite"}:
            if db.bind.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            statement = insert(GumrukEmsalKararModel).values(rows)
            excluded = statement.excluded
            statement = statement.on_conflict_do_update(
                index_elements=["karar_tipi", "referans_no"],
                set_={key: getattr(excluded, key) for key in rows[0] if key not in {"karar_tipi", "referans_no"}},
            )
            db.execute(statement)
            db.commit()
            return {"inserted": inserted, "updated": updated}

        for item, values in zip(materialized, rows):
            record = db.query(GumrukEmsalKararModel).filter_by(
                karar_tipi="BTB", referans_no=item["btb_no"]
            ).first()
            if record is None:
                record = GumrukEmsalKararModel(**values)
                db.add(record)
            else:
                for key, value in values.items():
                    if key not in {"karar_tipi", "referans_no"}:
                        setattr(record, key, value)
        db.commit()
    return {"inserted": inserted, "updated": updated}


def run(start: dt.date = dt.date(2020, 1, 1), end: Optional[dt.date] = None, delay: float = 0.2) -> Dict[str, int]:
    end = end or dt.date.today()
    init_orm_tables()
    totals = {"inserted": 0, "updated": 0, "months": 0, "failed_months": 0}
    with build_http_session() as session:
        for window in iter_month_windows(start, end):
            try:
                stats = upsert_batch(scrape_month(session, window, delay=delay))
                totals["inserted"] += stats["inserted"]
                totals["updated"] += stats["updated"]
                totals["months"] += 1
                logger.info("%s..%s tamamlandı: %s", window.start, window.end, stats)
            except Exception:
                totals["failed_months"] += 1
                logger.exception("Aylık BTB penceresi başarısız: %s..%s", window.start, window.end)
    return totals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=dt.date.fromisoformat, default=dt.date(2020, 1, 1))
    parser.add_argument("--end", type=dt.date.fromisoformat, default=dt.date.today())
    parser.add_argument("--delay", type=float, default=0.2)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print(json.dumps(run(args.start, args.end, args.delay), ensure_ascii=False))


if __name__ == "__main__":
    main()
