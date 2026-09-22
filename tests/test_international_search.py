"""Unit tests for International Customs Rulings Search and Schemas."""

import pathlib

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.modules.international_search import (
    generate_portal_links,
    search_international_rulings,
)
from api.schemas.product import InternationalRuling, GTIPDecision


def test_international_ruling_schema():
    ruling = InternationalRuling(
        country="US",
        ruling_no="NY N320145",
        hs_code="8518.30.20",
        product_description="Wireless Bluetooth headphones with microphone",
        legal_justification="Classified under HTSUS 8518.30 pursuant to GRI 1 and GRI 6.",
        summary_tr="ABD CBP Kararı: Ürün 8518.30 alt pozisyonunda sınıflandırılmıştır.",
        issue_date="2024-01-15",
        source_url="https://www.customsmobile.com/rulings/search?q=NY+N320145",
        source_name="ABD CBP CROSS (CustomsMobile)",
        similarity_score=0.92,
    )
    assert ruling.country == "US"
    assert ruling.ruling_no == "NY N320145"
    assert "8518.30" in ruling.hs_code


def test_generate_portal_links():
    links = generate_portal_links("laptop computer", "8471.30")
    assert "customsmobile.com" in links["us_customsmobile"]
    assert "ec.europa.eu" in links["eu_ebti"]
    assert "gjzwfw.gov.cn" in links["cn_gacc"]


def test_no_fabricated_ruling_generator_exists():
    """Uydurma emsal karar üreticisi kalıcı olarak kaldırıldı."""
    import api.modules.international_search as intl

    assert not hasattr(intl, "_build_fallback_rulings")
    source = pathlib.Path(intl.__file__).read_text(encoding="utf-8")

    # Modül InternationalRuling'i YALNIZ modelin döndürdüğü veriden kurabilir.
    # Literal alanlarla kurulan her örnek uydurma emsal demektir.
    constructions = [
        line.strip() for line in source.splitlines() if "InternationalRuling(" in line
    ]
    assert constructions == ["rulings.append(InternationalRuling(**item))"], constructions


def test_search_returns_empty_when_live_search_unavailable():
    """Emülatör/erişimsiz ortamda uydurma karar değil, boş liste dönmeli."""
    results = search_international_rulings("kablosuz kulaklık", hs_code_hint="8518.30", max_results=3)
    assert results == []


def test_search_returns_empty_when_provider_raises(monkeypatch):
    """Canlı arama hata verirse sistem sessizce sahte emsal üretmemeli."""
    import api.modules.international_search as intl

    monkeypatch.setattr(intl.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(intl.settings, "GCP_PROJECT_ID", "test-project")

    def _boom():
        raise TimeoutError("504 DEADLINE_EXCEEDED")

    monkeypatch.setattr("api.modules.vertex_client.get_grounded_search_client", _boom)

    results = search_international_rulings("kablosuz kulaklık", hs_code_hint="8518.30")
    assert results == []


def test_decision_never_carries_fabricated_intl_legal_sources():
    """Emsal yokken karara hiçbir INTL_* hukuki kaynak girmemeli."""
    from api.graph.workflow import workflow_engine

    decision = workflow_engine.start_analysis("ahşap sandalye")
    intl_sources = [s for s in decision.legal_sources if s.source_type.startswith("INTL_")]
    assert intl_sources == []
    assert decision.international_rulings == []


def test_international_search_api_endpoint():
    client = TestClient(app)
    response = client.post(
        "/api/v1/precedents/international-search",
        json={
            "product_text": "Taşınabilir dizüstü bilgisayar 16GB RAM 512GB SSD",
            "hs_code": "8471.30",
            "target_countries": ["US", "CN", "EU"],
            "max_results": 3,
        },
    )
    assert response.status_code == 200
    data = response.json()
    # Emülatör/test ortamında canlı arama yapılamaz; uydurma emsal DÖNMEMELİ.
    assert data["total_found"] == 0
    assert data["rulings"] == []
    # Kullanıcı araştırmayı sürdürebilsin diye portal bağlantıları her durumda döner.
    assert "portal_links" in data
    assert "us_customsmobile" in data["portal_links"]
    assert "cn_gacc" in data["portal_links"]
    assert "eu_ebti" in data["portal_links"]

