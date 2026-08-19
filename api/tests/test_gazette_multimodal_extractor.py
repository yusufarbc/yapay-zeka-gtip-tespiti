import pytest
import os
import sys
import json
from unittest.mock import patch, MagicMock

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from scripts.extract_official_gazette_exact import (
    CustomsDecisionItem, 
    GazetteExtractionResult, 
    extract_tables_from_gazette_pdf
)
from scripts.spider_resmi_gazete_archive import (
    load_checkpoint,
    save_checkpoint,
    LOCAL_CHECKPOINT_PATH
)


def test_customs_decision_item_schema_validation():
    """CustomsDecisionItem Pydantic modelinin alanlarını ve doğruluğunu test eder."""
    item = CustomsDecisionItem(
        karar_no="1",
        gtip_kodu="4411.13.90.00.11",
        esya_tanimi="Emprenye edilmiş dekor kağıdı ile kaplanmış, yoğunluğu 0.85 g/cm3, kalınlığı 8 mm olan HDF esaslı laminat parke yer döşemesi.",
        hukuki_gerekce="GİR 1, GİR 6 ve TGTC Fasıl 44 İzahname Notları uyarınca 4411.13 pozisyonunda sınıflandırılmıştır.",
        resmi_gazete_sayisi="31793",
        yayin_tarihi="2022-03-29"
    )
    assert item.gtip_kodu == "4411.13.90.00.11"
    assert "laminat parke" in item.esya_tanimi
    assert "GİR 1" in item.hukuki_gerekce
    assert item.resmi_gazete_sayisi == "31793"
    assert item.yayin_tarihi == "2022-03-29"


def test_laminate_flooring_multimodal_table_extraction():
    """
    Laminat parke sınıflandırma kararının mock multimodal PDF yanıtı ile
    eksiksiz teknik tanım ve GİR gerekçesiyle ayrıştırıldığını doğrular.
    """
    mock_items = [
        CustomsDecisionItem(
            karar_no="1",
            gtip_kodu="4411.13.90.00.11",
            esya_tanimi="Her iki yüzü melamin reçinesi emdirilmiş kağıtla kaplı, kenarları lamba ve zıvana şeklinde profillendirilmiş, yoğunluğu 0.86 g/cm3, kalınlığı 8.3 mm olan lif levha (Laminat Parke)",
            hukuki_gerekce="Tarife Yorumu ile İlgili Genel Kuralların 1 ve 6 ncı maddeleri, 44.11 Tarife Pozisyonu İzahnamesi",
            resmi_gazete_sayisi="31793",
            yayin_tarihi="2022-03-29"
        )
    ]
    
    mock_response = MagicMock()
    mock_response.parsed = GazetteExtractionResult(items=mock_items)

    with patch("scripts.extract_official_gazette_exact.get_genai_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        dummy_pdf_bytes = b"%PDF-1.4 dummy laminate flooring content for testing" * 10
        results = extract_tables_from_gazette_pdf(
            pdf_bytes=dummy_pdf_bytes,
            pub_date="2022-03-29",
            gazette_no="31793"
        )

        assert len(results) == 1
        item = results[0]
        assert item.gtip_kodu == "4411.13.90.00.11"
        # Jenerik tek kelimelik başlık değil, detaylı teknik açıklama olmalı
        assert len(item.esya_tanimi) > 50
        assert "yoğunluğu" in item.esya_tanimi or "lamba" in item.esya_tanimi
        # Tebliğ preamble (Madde 1) değil, GİR kuralları gerekçe olmalı
        assert "Genel Kuralların 1 ve 6" in item.hukuki_gerekce


def test_electric_kettle_multimodal_table_extraction():
    """
    Su ısıtıcısı (kettle) sınıflandırma kararının teknik parametrelerinin korunduğunu test eder.
    """
    mock_items = [
        CustomsDecisionItem(
            karar_no="2",
            gtip_kodu="8516.79.70.00.00",
            esya_tanimi="Paslanmaz çelik gövdeli, gizli rezistanslı, 1.7 litre su kapasiteli, 2200 W gücünde, tabandan ayrılabilir elektrikli su ısıtıcısı (kettle).",
            hukuki_gerekce="GİR 1 ve GİR 6 gereğince 8516 pozisyonu.",
            resmi_gazete_sayisi="32000",
            yayin_tarihi="2022-11-01"
        )
    ]
    
    mock_response = MagicMock()
    mock_response.parsed = GazetteExtractionResult(items=mock_items)

    with patch("scripts.extract_official_gazette_exact.get_genai_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        dummy_pdf_bytes = b"%PDF-1.4 dummy kettle content" * 10
        results = extract_tables_from_gazette_pdf(
            pdf_bytes=dummy_pdf_bytes,
            pub_date="2022-11-01",
            gazette_no="32000"
        )

        assert len(results) == 1
        item = results[0]
        assert item.gtip_kodu == "8516.79.70.00.00"
        assert "2200 W" in item.esya_tanimi or "rezistans" in item.esya_tanimi
        assert "GİR 1" in item.hukuki_gerekce


def test_etl_checkpoint_save_and_load(tmp_path):
    """ETL checkpoint kaydetme ve okuma mekanizmasını test eder."""
    test_state = {
        "last_processed_date": "2023-05-15",
        "total_processed_days": 150,
        "total_saved_records": 42
    }
    
    save_checkpoint(test_state)
    loaded = load_checkpoint()

    assert loaded.get("last_processed_date") == "2023-05-15"
    assert loaded.get("total_processed_days") == 150
    assert loaded.get("total_saved_records") == 42
    assert "last_updated_at" in loaded
