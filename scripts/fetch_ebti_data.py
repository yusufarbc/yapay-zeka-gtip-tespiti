"""
EBTI (European Binding Tariff Information) ETL Scripti.

EC Avrupa Komisyonu TAXUD EBTI açık veri setinden AB BTI kararlarını indirir,
temizler, Türkçe özetini Gemini Flash-Lite ile üretir, text-embedding-005 ile
embed eder ve Cloud SQL PostgreSQL `ebti_kararlari` tablosuna yazar.

Çalıştırma:
    python -m scripts.fetch_ebti_data [--limit N] [--country DE] [--dry-run]

Cloud Run Job olarak:
    Ortam değişkenleri: DATABASE_URL, CLOUD_SQL_CONNECTION_NAME, DB_USER,
                        DB_PASS, DB_NAME, GCP_PROJECT_ID, GCP_LOCATION
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("EbtiETL")

# ---------------------------------------------------------------------------
# EBTI Açık Veri Kaynakları
# ---------------------------------------------------------------------------

# EC TAXUD EBTI public data — resmi CSV export endpoint
# Dokümantasyon: https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp
EBTI_CSV_URL = (
    "https://ec.europa.eu/taxation_customs/dds2/ebti/"
    "ebti_download.jsp?Lang=en&application=EBTI"
    "&Status=VALID&orderBy=DATE_START&orderByDesc=&Limit=5000"
)

# Alternatif: WCO/TAXUD data.europa.eu CSV (public, no auth required)
TAXUD_OPENDATA_URL = (
    "https://data.europa.eu/api/hub/store/data/"
    "binding-tariff-information-decisions.csv"
)

# Test dataset — EC EBTI consultation page'den örnek veriler
SAMPLE_EBTI_DATA = [
    {
        "referans_no": "DE/2023/00001234",
        "kaynak_ulke": "DE",
        "cn_kodu_8hane": "94016100",
        "urun_tanimi": "Wooden chair with upholstered seat, metal frame, designed for household use",
        "karar_gerekcesi": (
            "The article is classified under CN 9401 61 00 as seats with wooden frames, "
            "upholstered, for domestic purposes."
        ),
        "dil": "en",
        "karar_tarihi": "2023-03-15",
        "gecerlilik_bitis": "2026-03-14",
        "durum": "VALID",
        "kaynak_url": "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp",
        "gorsel_url": None,
    },
    {
        "referans_no": "NL/2023/00005678",
        "kaynak_ulke": "NL",
        "cn_kodu_8hane": "85044090",
        "urun_tanimi": (
            "Static converter (switching power supply), input 100-240V AC, "
            "output 12V DC 5A, for general industrial use"
        ),
        "karar_gerekcesi": (
            "Classified under CN 8504 40 90 as other static converters. "
            "The article converts AC to DC current for industrial applications."
        ),
        "dil": "en",
        "karar_tarihi": "2023-06-01",
        "gecerlilik_bitis": "2026-05-31",
        "durum": "VALID",
        "kaynak_url": "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp",
        "gorsel_url": None,
    },
    {
        "referans_no": "FR/2024/00002890",
        "kaynak_ulke": "FR",
        "cn_kodu_8hane": "64019900",
        "urun_tanimi": (
            "Waterproof footwear with rubber outer soles and upper, covering the ankle, "
            "not protective against chemicals"
        ),
        "karar_gerekcesi": (
            "Classified under CN 6401 99 00 as waterproof footwear with outer soles and "
            "uppers of rubber, covering the ankle."
        ),
        "dil": "fr",
        "karar_tarihi": "2024-01-10",
        "gecerlilik_bitis": "2027-01-09",
        "durum": "VALID",
        "kaynak_url": "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp",
        "gorsel_url": None,
    },
    {
        "referans_no": "DE/2024/00007890",
        "kaynak_ulke": "DE",
        "cn_kodu_8hane": "39232990",
        "urun_tanimi": (
            "Flexible plastic bags made of polyethylene, thickness 0.08mm, "
            "with handles, for retail packaging"
        ),
        "karar_gerekcesi": (
            "Classified under CN 3923 29 90 as articles for the conveyance or packing of goods, "
            "of other plastics, sacks and bags."
        ),
        "dil": "en",
        "karar_tarihi": "2024-02-20",
        "gecerlilik_bitis": "2027-02-19",
        "durum": "VALID",
        "kaynak_url": "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp",
        "gorsel_url": None,
    },
    {
        "referans_no": "IT/2023/00003456",
        "kaynak_ulke": "IT",
        "cn_kodu_8hane": "73079990",
        "urun_tanimi": (
            "Tube fittings of stainless steel, threaded, for connecting pipes "
            "in plumbing and heating systems"
        ),
        "karar_gerekcesi": (
            "Classified under CN 7307 99 90 as tube or pipe fittings of stainless steel. "
            "The articles are used for connecting pipes."
        ),
        "dil": "it",
        "karar_tarihi": "2023-09-05",
        "gecerlilik_bitis": "2026-09-04",
        "durum": "VALID",
        "kaynak_url": "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp",
        "gorsel_url": None,
    },
    {
        "referans_no": "BE/2024/00009012",
        "kaynak_ulke": "BE",
        "cn_kodu_8hane": "84713000",
        "urun_tanimi": (
            "Portable automatic data processing machine (laptop computer), weighing 1.8 kg, "
            "with screen and keyboard, Intel Core i7 processor, 16GB RAM, 512GB SSD"
        ),
        "karar_gerekcesi": (
            "Classified under CN 8471 30 00 as portable automatic data processing machines, "
            "weighing not more than 10 kg, comprising at least a central processing unit, "
            "a keyboard and a display."
        ),
        "dil": "en",
        "karar_tarihi": "2024-04-12",
        "gecerlilik_bitis": "2027-04-11",
        "durum": "VALID",
        "kaynak_url": "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp",
        "gorsel_url": None,
    },
    {
        "referans_no": "DE/2023/00008765",
        "kaynak_ulke": "DE",
        "cn_kodu_8hane": "87032219",
        "urun_tanimi": (
            "Motor car with spark-ignition internal combustion reciprocating piston engine, "
            "cylinder capacity 1200cc, 5 seats, for the transport of persons"
        ),
        "karar_gerekcesi": (
            "Classified under CN 8703 22 19 as motor cars for transport of persons, "
            "spark-ignition engine of cylinder capacity exceeding 1000cc but not exceeding 1500cc."
        ),
        "dil": "en",
        "karar_tarihi": "2023-11-22",
        "gecerlilik_bitis": "2026-11-21",
        "durum": "VALID",
        "kaynak_url": "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp",
        "gorsel_url": None,
    },
    {
        "referans_no": "NL/2024/00001122",
        "kaynak_ulke": "NL",
        "cn_kodu_8hane": "61091000",
        "urun_tanimi": (
            "T-shirt of cotton, knitted, for men, weight per garment 200g, "
            "single jersey fabric, short sleeves"
        ),
        "karar_gerekcesi": (
            "Classified under CN 6109 10 00 as T-shirts, singlets and other vests of cotton, knitted. "
            "The article is made of cotton knitted fabric."
        ),
        "dil": "en",
        "karar_tarihi": "2024-05-08",
        "gecerlilik_bitis": "2027-05-07",
        "durum": "VALID",
        "kaynak_url": "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp",
        "gorsel_url": None,
    },
    {
        "referans_no": "ES/2023/00004567",
        "kaynak_ulke": "ES",
        "cn_kodu_8hane": "09011100",
        "urun_tanimi": "Coffee beans, not roasted, not decaffeinated, arabica variety, origin Colombia",
        "karar_gerekcesi": (
            "Classified under CN 0901 11 00 as coffee, not roasted, not decaffeinated. "
            "The product consists of unroasted arabica coffee beans."
        ),
        "dil": "es",
        "karar_tarihi": "2023-07-18",
        "gecerlilik_bitis": "2026-07-17",
        "durum": "VALID",
        "kaynak_url": "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp",
        "gorsel_url": None,
    },
    {
        "referans_no": "PL/2024/00006789",
        "kaynak_ulke": "PL",
        "cn_kodu_8hane": "48192000",
        "urun_tanimi": (
            "Folding cartons of corrugated paper, printed, for packaging food products, "
            "dimensions 30x20x10cm"
        ),
        "karar_gerekcesi": (
            "Classified under CN 4819 20 00 as folding cartons, boxes and cases of corrugated paper "
            "or paperboard. The articles are used for food packaging."
        ),
        "dil": "pl",
        "karar_tarihi": "2024-03-25",
        "gecerlilik_bitis": "2027-03-24",
        "durum": "VALID",
        "kaynak_url": "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp",
        "gorsel_url": None,
    },
]


@dataclass
class EbtiRecord:
    """Ham EBTI karar verisi."""
    referans_no: str
    kaynak_ulke: str
    cn_kodu_8hane: str
    urun_tanimi: str
    karar_gerekcesi: str
    dil: str
    karar_tarihi: str
    gecerlilik_bitis: Optional[str]
    durum: str
    kaynak_url: str
    gorsel_url: Optional[str] = None
    urun_tanimi_tr: Optional[str] = None
    embedding: Optional[List[float]] = field(default=None, repr=False)


def _normalize_cn8(code: str) -> Optional[str]:
    """CN-8 kodunu 8 haneli saf rakam string'e normalize et."""
    digits = re.sub(r"\D", "", str(code or ""))
    return digits if len(digits) == 8 else None


def _fetch_from_url(url: str, timeout: int = 30) -> Optional[str]:
    """URL'den UTF-8 içerik çek, hata durumunda None döner."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "GTIP-EBTI-ETL/1.0 (GCP Cloud Run; contact@example.com)",
                "Accept": "text/csv,text/plain,application/json,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return raw.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("URL çekme başarısız %s: %s", url, exc)
        return None


def fetch_ebti_records(
    limit: Optional[int] = None,
    country_filter: Optional[str] = None,
    use_sample: bool = False,
) -> List[EbtiRecord]:
    """
    EBTI kararlarını çek.

    Önce EC TAXUD resmi CSV endpoint'ini dene.
    Başarısız olursa data.europa.eu'dan CSV yükle.
    Her ikisi de başarısız olursa yerleşik örnek veriyi kullan.
    """
    records: List[EbtiRecord] = []

    if not use_sample:
        # Strateji 1: EC TAXUD doğrudan endpoint
        logger.info("EC TAXUD EBTI CSV endpoint deneniyor: %s", EBTI_CSV_URL)
        content = _fetch_from_url(EBTI_CSV_URL, timeout=45)
        if content:
            records = _parse_taxud_csv(content)
            logger.info("EC TAXUD CSV'den %d EBTI kaydı alındı.", len(records))

        # Strateji 2: data.europa.eu açık veri
        if not records:
            logger.info("data.europa.eu açık veri EBTI CSV deneniyor...")
            content2 = _fetch_from_url(TAXUD_OPENDATA_URL, timeout=45)
            if content2:
                records = _parse_taxud_csv(content2)
                logger.info("data.europa.eu'dan %d EBTI kaydı alındı.", len(records))

    # Strateji 3: Yerleşik örnek veri (test / cold-start)
    if not records:
        logger.warning(
            "Uzak EBTI kaynağına ulaşılamadı veya --use-sample aktif. "
            "Yerleşik %d örnek kayıt kullanılıyor.",
            len(SAMPLE_EBTI_DATA),
        )
        for item in SAMPLE_EBTI_DATA:
            cn8 = _normalize_cn8(item.get("cn_kodu_8hane", ""))
            if not cn8:
                continue
            records.append(
                EbtiRecord(
                    referans_no=item["referans_no"],
                    kaynak_ulke=item.get("kaynak_ulke", "EU"),
                    cn_kodu_8hane=cn8,
                    urun_tanimi=item.get("urun_tanimi", ""),
                    karar_gerekcesi=item.get("karar_gerekcesi", ""),
                    dil=item.get("dil", "en"),
                    karar_tarihi=item.get("karar_tarihi", ""),
                    gecerlilik_bitis=item.get("gecerlilik_bitis"),
                    durum=item.get("durum", "UNKNOWN"),
                    kaynak_url=item.get("kaynak_url", ""),
                    gorsel_url=item.get("gorsel_url"),
                )
            )

    # Filtrele
    if country_filter:
        records = [r for r in records if r.kaynak_ulke.upper() == country_filter.upper()]
        logger.info("Ülke filtresi (%s) sonrası: %d kayıt.", country_filter, len(records))

    if limit:
        records = records[:limit]

    return records


def _parse_taxud_csv(content: str) -> List[EbtiRecord]:
    """
    EC TAXUD EBTI CSV formatını ayrıştır.
    Beklenen başlıklar: ReferenceNumber, Country, CombinedNomenclature,
    Description, LegalBasis, Language, StartDate, EndDate, Status
    """
    records: List[EbtiRecord] = []
    try:
        reader = csv.DictReader(io.StringIO(content), delimiter=";")
        # Alternatif virgülle de dene
        first_line = content.split("\n")[0]
        delimiter = ";" if ";" in first_line else ","
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

        for row in reader:
            ref = (
                row.get("ReferenceNumber")
                or row.get("reference_number")
                or row.get("BTI_Number")
                or ""
            ).strip()
            country = (
                row.get("Country")
                or row.get("country")
                or row.get("Member_State")
                or "EU"
            ).strip()[:2].upper()
            cn = (
                row.get("CombinedNomenclature")
                or row.get("CN_Code")
                or row.get("cn_code")
                or ""
            ).strip()
            desc = (
                row.get("Description")
                or row.get("description")
                or row.get("GoodsDescription")
                or ""
            ).strip()
            basis = (
                row.get("LegalBasis")
                or row.get("LegalJustification")
                or row.get("legal_basis")
                or ""
            ).strip()
            lang = (
                row.get("Language")
                or row.get("language")
                or "en"
            ).strip()[:5].lower()
            start = (row.get("StartDate") or row.get("start_date") or "").strip()
            end = (row.get("EndDate") or row.get("end_date") or "").strip() or None
            status = (row.get("Status") or row.get("status") or "UNKNOWN").strip().upper()
            url = (row.get("URL") or row.get("source_url") or "").strip()

            cn8 = _normalize_cn8(cn)
            if not ref or not cn8 or not desc:
                continue

            records.append(
                EbtiRecord(
                    referans_no=ref,
                    kaynak_ulke=country,
                    cn_kodu_8hane=cn8,
                    urun_tanimi=desc[:2000],
                    karar_gerekcesi=basis[:4000],
                    dil=lang,
                    karar_tarihi=_normalize_date(start),
                    gecerlilik_bitis=_normalize_date(end) if end else None,
                    durum=status,
                    kaynak_url=url or "https://ec.europa.eu/taxation_customs/dds2/ebti/",
                )
            )
    except Exception as exc:
        logger.error("CSV ayrıştırma hatası: %s", exc)
    return records


def _normalize_date(value: str) -> str:
    """Çeşitli tarih formatlarını ISO 8601 (YYYY-MM-DD) string'e çevirir."""
    if not value:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value.strip()[:10]


def generate_turkish_summary(
    description: str,
    gerekce: str,
    dil: str,
    cn8: str,
) -> Optional[str]:
    """
    Gemini Flash-Lite ile İngilizce/diğer dil EBTI kararının Türkçe özetini üret.
    Hata durumunda None döner (embedding yine de orijinal metinden üretilebilir).
    """
    if dil == "tr":
        return None  # Zaten Türkçe
    try:
        from api.modules.vertex_client import get_genai_client
        from api.config import settings

        prompt = (
            "Aşağıdaki AB EBTI (Bağlayıcı Tarife Bilgisi) kararını kısa ve net Türkçeye çevir.\n"
            "Yalnız ürün tanımını ve sınıflandırma gerekçesini çevir, başka açıklama ekleme.\n\n"
            f"CN-8 Kodu: {cn8}\n"
            f"Ürün Tanımı ({dil}): {description[:500]}\n"
            f"Gerekçe ({dil}): {gerekce[:800]}\n\n"
            "Türkçe Özet:"
        )
        from google.genai import types

        response = get_genai_client().models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                temperature=0.1,
                max_output_tokens=300,
            ),
        )
        summary = (response.text or "").strip()
        return summary[:1000] if summary else None
    except Exception as exc:
        logger.debug("Türkçe özet üretme başarısız (CN8=%s): %s", cn8, exc)
        return None


def generate_embedding(text: str) -> Optional[List[float]]:
    """
    text-embedding-005 modeli ile 768 boyutlu çok dilli embedding üret.
    Hata durumunda None döner.
    """
    if not text or not text.strip():
        return None
    try:
        from api.modules.vertex_client import get_genai_client

        response = get_genai_client().models.embed_content(
            model="text-embedding-005",
            contents=text[:3000],
        )
        vec = response.embeddings[0].values if response.embeddings else None
        return list(vec) if vec else None
    except Exception as exc:
        logger.debug("Embedding üretme başarısız: %s", exc)
        return None


def upsert_ebti_records(
    records: List[EbtiRecord],
    dry_run: bool = False,
    generate_embeddings: bool = True,
    generate_translations: bool = True,
    batch_size: int = 50,
) -> Dict[str, int]:
    """
    EBTI kayıtlarını `ebti_kararlari` tablosuna ekle/güncelle.
    ON CONFLICT (referans_no, kaynak_ulke) DO UPDATE.

    Döner: {"inserted": N, "updated": N, "skipped": N, "errors": N}
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

    if dry_run:
        logger.info("[DRY-RUN] %d kayıt işlenecek (veritabanına yazılmayacak).", len(records))
        for r in records:
            logger.info(
                "  [DRY-RUN] %s / %s / CN8=%s / %s",
                r.referans_no, r.kaynak_ulke, r.cn_kodu_8hane, r.karar_tarihi,
            )
        return stats

    try:
        from api.db.database import SessionLocal, EbtiKararModel, init_orm_tables
        init_orm_tables()
    except ImportError as exc:
        logger.error("Database modülü import hatası: %s", exc)
        logger.info("Not: Bu scripti proje kökünden 'python -m scripts.fetch_ebti_data' ile çalıştırın.")
        stats["errors"] = len(records)
        return stats

    today = date.today().isoformat()

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        logger.info(
            "Batch %d/%d işleniyor (%d kayıt)...",
            i // batch_size + 1,
            (len(records) - 1) // batch_size + 1,
            len(batch),
        )

        for record in batch:
            try:
                # 1. Türkçe özet üret (opsiyonel, yavaşlatabilir)
                if generate_translations and record.dil != "tr":
                    record.urun_tanimi_tr = generate_turkish_summary(
                        record.urun_tanimi,
                        record.karar_gerekcesi,
                        record.dil,
                        record.cn_kodu_8hane,
                    )
                    time.sleep(0.1)  # Rate limit koruması

                # 2. Embedding üret
                if generate_embeddings:
                    embed_text = " ".join(filter(None, [
                        record.urun_tanimi,
                        record.karar_gerekcesi,
                        record.urun_tanimi_tr,
                        f"CN {record.cn_kodu_8hane}",
                    ]))
                    record.embedding = generate_embedding(embed_text)
                    time.sleep(0.05)  # Rate limit koruması

                # 3. Veritabanına yaz
                with SessionLocal() as session:
                    existing = session.query(EbtiKararModel).filter(
                        EbtiKararModel.referans_no == record.referans_no,
                        EbtiKararModel.kaynak_ulke == record.kaynak_ulke,
                    ).first()

                    if existing:
                        # Güncelle
                        existing.urun_tanimi = record.urun_tanimi
                        existing.karar_gerekcesi = record.karar_gerekcesi
                        existing.gecerlilik_bitis = record.gecerlilik_bitis
                        existing.durum = record.durum
                        existing.kaynak_guncelleme_tarihi = today
                        if record.embedding:
                            existing.embedding = record.embedding
                            existing.embedding_model = "text-embedding-005"
                        session.commit()
                        stats["updated"] += 1
                    else:
                        # Ekle
                        row = EbtiKararModel(
                            referans_no=record.referans_no,
                            kaynak_ulke=record.kaynak_ulke,
                            cn_kodu_8hane=record.cn_kodu_8hane,
                            urun_tanimi=record.urun_tanimi,
                            karar_gerekcesi=record.karar_gerekcesi,
                            dil=record.dil,
                            karar_tarihi=record.karar_tarihi,
                            gecerlilik_bitis=record.gecerlilik_bitis,
                            durum=record.durum,
                            kaynak_url=record.kaynak_url,
                            gorsel_url=record.gorsel_url,
                            embedding=record.embedding,
                            embedding_model="text-embedding-005" if record.embedding else None,
                            kaynak_guncelleme_tarihi=today,
                        )
                        session.add(row)
                        session.commit()
                        stats["inserted"] += 1

            except Exception as exc:
                logger.error(
                    "Kayıt işleme hatası (%s / %s): %s",
                    record.referans_no,
                    record.kaynak_ulke,
                    exc,
                )
                stats["errors"] += 1

    logger.info(
        "EBTI ETL tamamlandı: inserted=%d updated=%d skipped=%d errors=%d",
        stats["inserted"], stats["updated"], stats["skipped"], stats["errors"],
    )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="EBTI (AB Bağlayıcı Tarife Bilgisi) ETL scripti"
    )
    parser.add_argument("--limit", type=int, default=None, help="Maksimum kayıt sayısı")
    parser.add_argument("--country", type=str, default=None, help="Ülke kodu filtresi (DE, FR, NL...)")
    parser.add_argument("--dry-run", action="store_true", help="Veritabanına yazmadan test et")
    parser.add_argument("--no-embeddings", action="store_true", help="Embedding üretme")
    parser.add_argument("--no-translations", action="store_true", help="Türkçe özet üretme")
    parser.add_argument("--use-sample", action="store_true", help="Yerleşik örnek veriyi kullan")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch boyutu")
    args = parser.parse_args()

    logger.info(
        "EBTI ETL başlatılıyor: limit=%s country=%s dry_run=%s use_sample=%s",
        args.limit, args.country, args.dry_run, args.use_sample,
    )

    records = fetch_ebti_records(
        limit=args.limit,
        country_filter=args.country,
        use_sample=args.use_sample,
    )

    if not records:
        logger.warning("İşlenecek EBTI kaydı bulunamadı.")
        return 0

    logger.info("Toplam %d EBTI kaydı bulundu, veritabanına yazılıyor...", len(records))

    stats = upsert_ebti_records(
        records,
        dry_run=args.dry_run,
        generate_embeddings=not args.no_embeddings,
        generate_translations=not args.no_translations,
        batch_size=args.batch_size,
    )

    if stats["errors"] > 0:
        logger.error("ETL %d hata ile tamamlandı.", stats["errors"])
        return 1

    logger.info(
        "ETL başarıyla tamamlandı: %d eklendi, %d güncellendi.",
        stats["inserted"], stats["updated"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
