from api.schemas.product import ProductFeatures
from api.modules.rule_engine import rule_engine
from api.graph.workflow import workflow_engine
from api.exporter import pdf_exporter
from api.config import settings

def test_rule_engine_gir3b():
    features = ProductFeatures(
        product_name="Pamuklu Dokuma Kumaş",
        primary_material="Pamuk",
        composition_percentages={"cotton": 0.60, "polyester": 0.40},
        intended_use="Tekstil"
    )
    allowed_chapters, rules = rule_engine.apply_rules(features)
    assert isinstance(allowed_chapters, list)
    assert len(rules) > 0

def test_workflow_end_to_end():
    decision = workflow_engine.start_analysis("Şarj edilebilir dahili 3.7V elektrik motorlu diş fırçası, ağırlığı 250 gram.")
    assert decision.session_id is not None
    assert decision.status in ["COMPLETED", "WAITING_FOR_USER", "MANUAL_REVIEW_REQUIRED"]

    # PDF Rapor Oluşturma
    pdf_bytes = pdf_exporter.generate_pdf_report(decision)
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 50

def test_security_auth_production_header_rejection():
    from unittest.mock import MagicMock
    from api.security.auth import get_current_user_session
    import pytest
    from fastapi import HTTPException

    req = MagicMock()
    req.headers = {"X-User-Email": "attacker@evil.com", "X-User-Role": "admin"}

    old_env = settings.ENVIRONMENT
    old_emu = settings.USE_GCP_EMULATOR
    try:
        # 1. Geliştirme modunda X-User-Email okunmalı
        settings.ENVIRONMENT = "development"
        dev_session = get_current_user_session(req)
        assert dev_session.email == "attacker@evil.com"

        # 2. Production modunda X-User-Email reddedilmeli ve 401 HTTPException fırlatılmalı (Demo Modu kapalıyken)
        settings.ENVIRONMENT = "production"
        settings.USE_GCP_EMULATOR = False
        settings.ALLOW_PUBLIC_DEMO_ACCESS = False
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_session(req)
        assert exc_info.value.status_code == 401
    finally:
        settings.ENVIRONMENT = old_env
        settings.USE_GCP_EMULATOR = old_emu

def test_hard_rules_matrix_lock():
    features = ProductFeatures(
        product_name="Hakiki Deri Erkek Ayakkabısı",
        primary_material="Deri",
        intended_use="Ayakkabı"
    )
    allowed_chapters, rules = rule_engine.apply_rules(features)
    assert "64" in allowed_chapters
    assert any("HARD LOCK" in r or "katı kural kilidi" in r.lower() for r in rules)

def test_hitl_5_percent_score_rule():
    from api.modules.deterministic_engine import deterministic_engine
    from api.schemas.product import GTIPCandidate
    from api.schemas.predicate import PredicateVerificationResult, PredicateStatus

    cand1 = GTIPCandidate(gtip_code="6403.51.05.00.00", chapter="64", heading="6403", description="Deri ayakkabı bilekleri örten", score=0.86)
    cand2 = GTIPCandidate(gtip_code="6403.59.05.00.00", chapter="64", heading="6403", description="Deri ayakkabı diğer", score=0.84)
    pred_results = [
        PredicateVerificationResult(predicate_id="P1", description="Deri mi?", status=PredicateStatus.TRUE, statute_reference="TGTC 6403")
    ]

    decision = deterministic_engine.evaluate_decision("test_sess", cand1, pred_results, candidates=[cand1, cand2])
    assert decision.status == "WAITING_FOR_USER"
    assert decision.hitl_question is not None
    assert len(decision.hitl_question.options) == 2
    assert "[A]" in decision.hitl_question.options[0].text
    assert "[B]" in decision.hitl_question.options[1].text

