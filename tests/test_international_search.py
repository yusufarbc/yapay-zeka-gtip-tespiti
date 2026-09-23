"""Uluslararası portal bağlantıları.

Bu modülde daha önce Gemini Google Search Grounding ile canlı karar araması
vardı; ölçüm kaldırılmasını gerektirdi (her çağrı 504, ~25 sn harcayıp sıfır
sonuç; yalın promptla bile 63 sn). Geriye kullanıcının araştırmayı kendisi
sürdürmesini sağlayan portal bağlantıları kaldı: model çağrısı yok.

Daha eski bir sürüm ise SAHTE karar numaraları (NY N…, Z2024-…) üretip bunları
karara hukuki dayanak olarak ekliyordu. Buradaki testler o davranışın hiçbir
biçimde geri gelmemesini güvenceye alır.
"""

import pathlib

from fastapi.testclient import TestClient

from api.main import app
from api.modules import international_search as intl
from api.modules.international_search import generate_portal_links


def test_portal_links_point_to_the_official_databases():
    links = generate_portal_links("laptop computer", "8471.30")
    assert "customsmobile.com" in links["us_customsmobile"]
    assert "rulings.cbp.gov" in links["us_cbp_cross"]
    assert "ec.europa.eu" in links["eu_ebti"]
    assert "gjzwfw.gov.cn" in links["cn_gacc"]


def test_portal_links_work_without_an_hs_code():
    links = generate_portal_links("ahşap sandalye")
    assert all(value.startswith("http") for value in links.values())


def test_query_is_url_encoded():
    """Türkçe karakter ve boşluk içeren sorgu bağlantıyı bozmamalı."""
    links = generate_portal_links("alüminyum doğrama cam balkon")
    assert " " not in links["eu_ebti"]
    assert "ü" not in links["eu_ebti"]


def test_module_makes_no_model_calls():
    """
    Canlı arama kaldırıldı: bu modül artık yalnız URL üretir. Bir model çağrısı
    geri gelirse gecikme ve 504'ler de geri gelir.
    """
    source = pathlib.Path(intl.__file__).read_text(encoding="utf-8")
    for forbidden in ("generate_content", "GoogleSearch", "get_genai_client",
                      "get_grounded_search_client"):
        assert forbidden not in source, f"model çağrısı geri gelmiş: {forbidden}"
    assert not hasattr(intl, "search_international_rulings")


def test_no_fabricated_ruling_generator_exists():
    """Sahte karar numarası üreten kod hiçbir biçimde geri gelmemeli."""
    source = pathlib.Path(intl.__file__).read_text(encoding="utf-8")
    assert not hasattr(intl, "_build_fallback_rulings")
    assert "InternationalRuling(" not in source


def test_decision_carries_portal_links_and_no_foreign_legal_sources():
    from api.graph.workflow import workflow_engine

    decision = workflow_engine.start_analysis("ahşap sandalye")
    foreign = [s for s in decision.legal_sources if s.source_type.startswith("INTL_")]
    assert foreign == []
    if decision.status == "COMPLETED":
        assert decision.research_portal_links, "portal bağlantıları dönmedi"


def test_removed_search_endpoint_is_gone():
    client = TestClient(app)
    response = client.post(
        "/api/v1/precedents/international-search",
        json={"product_text": "laptop"},
    )
    assert response.status_code == 404
