from api.schemas.product import ProductFeatures
from api.modules.rule_engine import rule_engine
from api.graph.workflow import workflow_engine
from api.exporter import pdf_exporter

def test_rule_engine_gir3b():
    features = ProductFeatures(
        product_name="Pamuklu Dokuma Kumaş",
        primary_material="Pamuk",
        composition_percentages={"cotton": 0.60, "polyester": 0.40},
        intended_use="Tekstil"
    )
    allowed_chapters, rules = rule_engine.apply_rules(features)
    assert "52" in allowed_chapters
    assert "55" not in allowed_chapters

def test_workflow_end_to_end():
    # 1. Diş Fırçası (Motorlu ev aleti)
    decision = workflow_engine.start_analysis("Şarj edilebilir dahili 3.7V elektrik motorlu diş fırçası, ağırlığı 250 gram.")
    assert decision.gtip_code == "8509.80.00.00.00"
    assert decision.status == "COMPLETED"
    assert decision.confidence_score >= 0.90

    # 2. PDF Rapor Oluşturma
    pdf_bytes = pdf_exporter.generate_pdf_report(decision)
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 50

def test_security_auth_production_header_rejection():
    from unittest.mock import MagicMock
    from api.security.auth import get_current_user_session
    from api.config import settings

    req = MagicMock()
    req.headers = {"X-User-Email": "attacker@evil.com", "X-User-Role": "admin"}
    
    # Geliştirme modunda X-User-Email okunmalı
    dev_session = get_current_user_session(req)
    assert dev_session.email == "attacker@evil.com"

    # Production modunda X-User-Email reddedilmeli ve 401 HTTPException fırlatılmalı
    import pytest
    from fastapi import HTTPException

    old_env = settings.ENVIRONMENT
    old_emu = settings.USE_GCP_EMULATOR
    try:
        settings.ENVIRONMENT = "production"
        settings.USE_GCP_EMULATOR = False
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_session(req)
        assert exc_info.value.status_code == 401
    finally:
        settings.ENVIRONMENT = old_env
        settings.USE_GCP_EMULATOR = old_emu
