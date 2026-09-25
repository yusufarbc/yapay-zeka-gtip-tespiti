"""Uluslararası arama kaldırıldı; geri gelmemeli.

Bu modülde önce Gemini Google Search Grounding ile canlı karar araması vardı;
ölçüm kaldırılmasını gerektirdi (her çağrı 504, ~25 sn harcayıp sıfır sonuç;
yalın promptla bile 63 sn). Ardından kalan portal bağlantıları da kaldırıldı:
sınıflandırmaya etkisi yoktu, yalnız gösterime giriyordu.

Daha eski bir sürüm ise SAHTE karar numaraları (NY N…, Z2024-…) üretip bunları
karara hukuki dayanak olarak ekliyordu. Buradaki testler o davranışın hiçbir
biçimde geri gelmemesini güvenceye alır.
"""

import importlib.util

from fastapi.testclient import TestClient

from api.main import app
from api.schemas.product import GTIPDecision


def test_international_search_module_is_gone():
    assert importlib.util.find_spec("api.modules.international_search") is None


def test_decision_schema_has_no_portal_links():
    assert "research_portal_links" not in GTIPDecision.model_fields


def test_decision_carries_no_foreign_legal_sources():
    from api.graph.workflow import workflow_engine

    decision = workflow_engine.start_analysis("ahşap sandalye")
    foreign = [s for s in decision.legal_sources if s.source_type.startswith("INTL_")]
    assert foreign == []


def test_removed_search_endpoint_is_gone():
    client = TestClient(app)
    response = client.post(
        "/api/v1/precedents/international-search",
        json={"product_text": "laptop"},
    )
    assert response.status_code == 404
