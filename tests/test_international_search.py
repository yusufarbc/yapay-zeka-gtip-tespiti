"""Unit tests for International Customs Rulings Search and Schemas."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.modules.international_search import (
    generate_portal_links,
    search_international_rulings,
    _build_fallback_rulings,
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


def test_build_fallback_rulings():
    rulings = _build_fallback_rulings("Ahşap yemek sandalyesi", hs_code_hint="9401.61")
    assert len(rulings) == 3
    countries = {r.country for r in rulings}
    assert countries == {"US", "CN", "EU"}
    assert any("customsmobile.com" in r.source_url for r in rulings)
    assert any("gjzwfw.gov.cn" in r.source_url for r in rulings)


def test_search_international_rulings_fallback():
    # In test/emulator mode, should return fallback rulings safely without network error
    results = search_international_rulings("kablosuz kulaklık", hs_code_hint="8518.30", max_results=3)
    assert len(results) <= 3
    assert len(results) > 0
    for r in results:
        assert isinstance(r, InternationalRuling)
        assert r.country in ["US", "CN", "EU"]


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
    assert data["total_found"] > 0
    assert len(data["rulings"]) > 0
    assert "portal_links" in data
    assert "us_customsmobile" in data["portal_links"]
    assert "cn_gacc" in data["portal_links"]
    assert "eu_ebti" in data["portal_links"]

