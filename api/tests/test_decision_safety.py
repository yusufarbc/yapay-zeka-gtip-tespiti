"""Fail-closed GTİP karar zinciri için güvenlik regresyonları."""

import json
from unittest.mock import MagicMock, patch

from api.config import settings
from api.graph.workflow import _condition_matches, _option_impact_value
from api.modules.context_cache_manager import context_cache_manager
from api.modules.deterministic_engine import deterministic_engine
from api.modules.llm_verifier import llm_verifier
from api.schemas.predicate import (
    CandidateSelectionStatus,
    PredicateStatus,
    PredicateVerificationResult,
)
from api.schemas.product import GTIPCandidate, LegalSource


def _candidate(code="9401.69.00.00.00", score=0.90):
    return GTIPCandidate(
        gtip_code=code,
        description="Ahşap iskeletli, döşemesiz oturmaya mahsus mobilya",
        chapter="94",
        heading="9401",
        score=score,
    )


def test_external_legal_source_fields_are_bounded_instead_of_crashing():
    source = LegalSource(
        source_type="btb" * 30,
        reference_no="R" * 300,
        title="T" * 1200,
        publication_date="2026-09-10" * 10,
    )
    assert len(source.source_type) == 50
    assert len(source.reference_no) == 150
    assert len(source.title) == 500
    assert len(source.publication_date) == 30


def test_false_required_predicate_can_never_complete():
    result = PredicateVerificationResult(
        predicate_id="P_REQUIRED",
        description="Zorunlu koşul",
        status=PredicateStatus.FALSE,
        required_value=PredicateStatus.TRUE,
        statute_reference="TGTC 9401",
    )
    decision = deterministic_engine.evaluate_decision("s", _candidate(), [result], [_candidate()])
    assert decision.status == "MANUAL_REVIEW_REQUIRED"
    assert decision.confidence_score < 0.50


def test_false_is_valid_only_when_rule_explicitly_requires_false():
    result = PredicateVerificationResult(
        predicate_id="P_NEGATIVE",
        description="Hariç tutulan özellik bulunmamalı",
        status=PredicateStatus.FALSE,
        required_value=PredicateStatus.FALSE,
        statute_reference="TGTC 9401 dışlama notu",
    )
    decision = deterministic_engine.evaluate_decision("s", _candidate(), [result], [_candidate()])
    assert decision.status == "COMPLETED"


def test_dynamic_rule_operators_compare_semantic_values():
    assert _condition_matches("9.5kg", "<=", "10kg") is True
    assert _condition_matches("11kg", "<=", "10kg") is False
    assert _condition_matches("evet", "==", "true") is True
    assert _condition_matches("%84", ">=", "85%") is False
    assert _option_impact_value({"id": "opt_gt_10kg"}) == "10.01kg"


def test_candidate_selector_rejects_out_of_set_choice(monkeypatch):
    monkeypatch.setattr(settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    response = MagicMock()
    response.text = json.dumps({
        "status": "SELECT",
        "selected_candidate_id": "C99",
        "reasoning_points": [],
        "missing_information": [],
        "evidence_source_refs": [],
    })
    client = MagicMock()
    client.models.generate_content.return_value = response
    with patch("api.modules.vertex_client.get_genai_client", return_value=client):
        selection = llm_verifier.select_candidate("ahşap sandalye", [_candidate()])
    assert selection.status == CandidateSelectionStatus.INSUFFICIENT_INFORMATION
    assert selection.selected_candidate_id is None


def test_tariff_verifier_rejects_missing_or_non_boolean_compliance(monkeypatch):
    monkeypatch.setattr(settings, "REASONING_LLM_MODEL", "gemini-2.5-flash")
    response = MagicMock()
    response.text = json.dumps({
        "candidate_gtip": "9401.69.00.00.00",
        "is_material_compliant": "false",
        # is_function_compliant intentionally missing
        "exclusion_notes_violated": False,
        "gir_rule_applied": "GIR 1",
        "legal_reasoning_points": [],
        "confidence_score": 0.99,
    })
    client = MagicMock()
    client.models.generate_content.return_value = response
    with patch("api.modules.vertex_client.get_genai_client", return_value=client):
        result = llm_verifier.verify_tariff_candidate(
            raw_text="ahşap sandalye",
            candidate_gtip="9401.69.00.00.00",
            heading_desc="Oturmaya mahsus mobilyalar",
        )
    assert result.confidence_score == 0.0
    assert result.is_material_compliant is False
    assert result.is_function_compliant is False
    assert result.gir_rule_applied == "MANUAL_REVIEW_REQUIRED"


def test_stale_cache_error_detection_is_specific():
    assert context_cache_manager.is_stale_cache_error(
        RuntimeError("404 NOT_FOUND cached content metadata")
    )
    assert not context_cache_manager.is_stale_cache_error(RuntimeError("429 quota exceeded"))
