"""
Official Gazette Exact Match Extraction Pipeline Unit Tests.
Verifies zero-hallucination exact string extraction, GTIP hygiene, and DB persistence.
"""

import pytest
from scripts.extract_official_gazette_exact import (
    DecisionBoundary,
    BoundariesList,
    extract_exact_text_from_boundaries,
    clean_and_validate_gtip,
    extract_and_save_official_gazette,
    find_decision_boundaries
)
from api.db.database import SessionLocal, GumrukSiniflandirmaKarariModel, GumrukEmsalKararModel, init_orm_tables

SAMPLE_OFFICIAL_GAZETTE_TEXT = """
T.C. TİCARET BAKANLIĞI
GÜMRÜKLER GENEL MÜDÜRLÜĞÜ
SINIFLANDIRMA KARARI

Resmi Gazete Tarihi: 20/11/2025  Sayı: 33100

Madde 1- Aşağıda özellikleri belirtilen eşya, Türk Gümrük Tarife Cetvelinin 8517.12.00.00.00 GTİP numarasında sınıflandırılmıştır.
Eşya Tanımı: Hücresel ağ üzerinden ses ve veri iletişimi sağlayan akıllı telefon.
Hukuki Gerekçe: Gümrük Genel Tebliği uyarınca, 8517.12.00.00.00 GTİP kodunda yer alan hücresel cihaz tanımına uyması nedeniyle bu pozisyona alınmıştır.

Madde 2- Aşağıda özellikleri belirtilen eşya, Türk Gümrük Tarife Cetvelinin 8471.60.70.00.00 GTİP numarasında sınıflandırılmıştır.
Eşya Tanımı: USB arabirimli mekanik klavye.
Hukuki Gerekçe: GIR 1 ve GIR 6 kuralları uyarınca girilmiş ve 8471.60.70.00.00 olarak tescil edilmiştir.
"""


def test_gtip_validation_hygiene():
    """GTİP kodlarının doğru temizlenip doğrulandığını test eder."""
    assert clean_and_validate_gtip("8517.12.00.00.00") == "851712000000"
    assert clean_and_validate_gtip("8471.60.70") == "84716070"
    assert clean_and_validate_gtip("8471.30") == "847130"
    assert clean_and_validate_gtip("851712000000") == "851712000000"
    
    # Geçersiz uzunluk veya rakam olmayanlar reddedilmeli
    assert clean_and_validate_gtip("12345") is None
    assert clean_and_validate_gtip("ABC85171200") is None
    assert clean_and_validate_gtip("") is None


def test_deterministic_string_slicing_exact():
    """LLM anchor'ları ile ham metinden birebir kopyalama yapıldığını doğrular."""
    boundary = DecisionBoundary(
        gtip_code="8517.12.00.00.00",
        start_anchor="Madde 1- Aşağıda özellikleri belirtilen eşya,",
        end_anchor="nedeniyle bu pozisyona alınmıştır."
    )

    extracted = extract_exact_text_from_boundaries(SAMPLE_OFFICIAL_GAZETTE_TEXT, boundary)
    assert extracted is not None
    # BİREBİR ALT DİZİ OLMA KONTROLÜ (Harfi Harfine)
    assert extracted in SAMPLE_OFFICIAL_GAZETTE_TEXT
    assert extracted.startswith("Madde 1-")
    assert extracted.endswith("nedeniyle bu pozisyona alınmıştır.")


def test_deterministic_string_slicing_fallback():
    """Anchor tam eşleşmezse regex fallback ile paragrafın harfi harfine kopyalandığını doğrular."""
    boundary = DecisionBoundary(
        gtip_code="8471.60.70.00.00",
        start_anchor="Yapay zeka uydurma başlangıç kelimeleri",
        end_anchor="Yapay zeka uydurma bitiş kelimeleri"
    )

    extracted = extract_exact_text_from_boundaries(SAMPLE_OFFICIAL_GAZETTE_TEXT, boundary)
    assert extracted is not None
    # Fallback metni de Orijinal Ham Metnin alt dizisi olmalıdır
    assert extracted in SAMPLE_OFFICIAL_GAZETTE_TEXT
    assert "8471.60.70.00.00" in extracted


def test_extract_and_save_official_gazette_end_to_end(monkeypatch):
    """ETL boru hattının uçtan uca çalışıp veritabanına birebir kaydettiğini test eder."""
    init_orm_tables()
    session = SessionLocal()

    # Çevrimdışı test için LLM Boundary Finder'ı mockla
    mock_boundaries = BoundariesList(items=[
        DecisionBoundary(
            gtip_code="8517.12.00.00.00",
            product_name="akıllı telefon",
            start_anchor="Madde 1- Aşağıda özellikleri belirtilen eşya,",
            end_anchor="nedeniyle bu pozisyona alınmıştır."
        ),
        DecisionBoundary(
            gtip_code="8471.60.70.00.00",
            product_name="mekanik klavye",
            start_anchor="Madde 2- Aşağıda özellikleri belirtilen eşya,",
            end_anchor="8471.60.70.00.00 olarak tescil edilmiştir."
        )
    ])
    monkeypatch.setattr("scripts.extract_official_gazette_exact.find_decision_boundaries", lambda raw: mock_boundaries)

    try:
        results = extract_and_save_official_gazette(
            raw_text=SAMPLE_OFFICIAL_GAZETTE_TEXT,
            yayin_tarihi="2025-11-20",
            resmi_gazete_sayisi="33100",
            kaynak_url="https://www.resmigazete.gov.tr/eskiler/2025/11/20251120-1.htm",
            db_session=session
        )

        assert len(results) >= 2

        for res in results:
            # HARFİ HARFİNE HALÜSİNASYONSUZLUK TESTİ
            assert res["hukuki_gerekce"] in SAMPLE_OFFICIAL_GAZETTE_TEXT

            # DB Kaydını Doğrula
            db_record = session.query(GumrukSiniflandirmaKarariModel).filter(
                GumrukSiniflandirmaKarariModel.gtip_kodu == res["gtip_kodu"],
                GumrukSiniflandirmaKarariModel.yayin_tarihi == "2025-11-20"
            ).first()

            assert db_record is not None
            assert db_record.hukuki_gerekce == res["hukuki_gerekce"]
            assert db_record.hukuki_gerekce in SAMPLE_OFFICIAL_GAZETTE_TEXT

            # Emsal Kararlar Senkronizasyonunu Doğrula
            emsal_record = session.query(GumrukEmsalKararModel).filter(
                GumrukEmsalKararModel.gtip_kodu == res["gtip_kodu"],
                GumrukEmsalKararModel.yayin_tarihi == "2025-11-20"
            ).first()
            assert emsal_record is not None

    finally:
        session.close()
