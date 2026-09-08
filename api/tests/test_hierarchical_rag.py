"""
Unit & Integration Tests for Hierarchical Hybrid RAG, pgvector database functions,
Chapter Exclusion Verification, and Structured Tariff Verification.
"""

import json
import datetime
import time
import pytest
from api.schemas.product import ProductFeatures, GTIPCandidate
from api.schemas.predicate import TariffVerification, ChapterExclusionCheck
from api.modules.rag_engine import rag_engine, CONSULTED_SOURCE_LAYERS
from api.modules.llm_verifier import llm_verifier
from api.graph.workflow import workflow_engine
from api.db.database import (
    SessionLocal, compute_rrf_score, hybrid_search_headings_and_gtip,
    search_chapter_notes_and_exclusions
)
from api.db.gcp_emulator import LocalVectorStore

def test_rrf_scoring_formula():
    """Reciprocal Rank Fusion (RRF) matematiksel formülünü doğrular."""
    # RRF(d) = sum(1 / (k + rank_i))
    score_1 = compute_rrf_score([1, 1], k=60) # 1/61 + 1/61
    expected_1 = (1.0 / 61.0) + (1.0 / 61.0)
    assert abs(score_1 - expected_1) < 1e-6

    # Rank 1 ve Rank 2
    score_2 = compute_rrf_score([1, 2], k=60)
    expected_2 = (1.0 / 61.0) + (1.0 / 62.0)
    assert abs(score_2 - expected_2) < 1e-6
    assert score_1 > score_2

def test_detect_candidate_chapters_with_hard_lock():
    """Katı kural kilidi (HARD LOCK) aktifken fasıl yönlendirmesinin o fasıldan ayrılmadığını doğrular."""
    chaps = rag_engine.detect_candidate_chapters(
        query_text="Deri erkek ayakkabısı",
        query_vector=None,
        allowed_chapters=["64"],
        is_hard_locked=True
    )
    assert chaps == ["64"]

def test_detect_candidate_chapters_dynamic():
    """Serbest metin aramasında dinamik fasıl tespitini doğrular."""
    chaps = rag_engine.detect_candidate_chapters(
        query_text="akıllı cep telefonu 5g hücresel",
        query_vector=None,
        allowed_chapters=None,
        is_hard_locked=False
    )
    assert len(chaps) >= 1
    assert any(c in ["85", "84", "90"] for c in chaps)

def test_filter_excluded_chapters():
    """Fasıl dışlama notları kontrolünü (Exclusion Check) doğrular."""
    # Fasıl 42 dışlama notu örneği: 'Ayakkabılar Fasıl 64'e girer, bu fasıl kapsamaz'
    exclusions = [
        "Bu fasıl aşağıdakileri kapsamaz: (a) Fasıl 64 kapsamındaki ayakkabılar ve bunların aksamı",
        "Bu fasıl oyuncakları kapsamaz (Fasıl 95)"
    ]
    check = llm_verifier.verify_chapter_exclusions(
        raw_text="Hakiki deri klasik erkek ayakkabısı kösele taban",
        chapter_code="42",
        exclusion_notes=exclusions
    )
    assert check.is_excluded == True
    assert check.recommended_alternative_chapter == "64"

def test_search_chapter_notes_and_exclusions_db():
    """Veritabanından fasıl notları ve dışlama hükümlerinin çekilmesini doğrular."""
    session = SessionLocal()
    try:
        res = search_chapter_notes_and_exclusions(session, ["64", "85"])
        assert isinstance(res, dict)
        assert "64" in res or "85" in res
    finally:
        session.close()

def test_hybrid_search_headings_and_gtip_db():
    """Cloud SQL / SQLite üzerinde hibrit (Dense + Sparse + RRF) pozisyon aramasını doğrular."""
    session = SessionLocal()
    try:
        results = hybrid_search_headings_and_gtip(
            session=session,
            query_text="telefon hücresel ağlar için",
            query_vector=None,
            allowed_chapters=["85"],
            top_k=5,
            rrf_k=60
        )
        assert isinstance(results, list)
        if results:
            first = results[0]
            assert "gtip_code" in first
            assert "rrf_score" in first
            assert "similarity_score" in first
    finally:
        session.close()


def test_precedent_search_separates_sources_and_enforces_six_year_window(monkeypatch):
    monkeypatch.setattr("api.db.gcp_emulator._get_embedding", lambda *_args, **_kwargs: None)
    store = LocalVectorStore()
    store._docs_cache = [
        {
            "btb_no": "TGTC2026-8516",
            "source_type": "TGTC_2026",
            "gtip_code": "8516",
            "chapter": "85",
            "heading": "8516",
            "issue_date": "2026-01-01",
            "product_description": "Elektrikli su ısıtıcıları",
        },
        {
            "btb_no": "BTB-NEW",
            "source_type": "BTB",
            "gtip_code": "8516.79.70.00.00",
            "chapter": "85",
            "heading": "8516",
            "issue_date": "2025-04-01",
            "product_description": "Elektrikli kettle su ısıtıcısı",
        },
        {
            "btb_no": "BTB-OLD",
            "source_type": "BTB",
            "gtip_code": "8516.79.70.00.00",
            "chapter": "85",
            "heading": "8516",
            "issue_date": "2018-01-01",
            "product_description": "Elektrikli kettle su ısıtıcısı",
        },
    ]
    store._docs_cache_loaded_at = time.monotonic()

    results = store.search_btb(
        "elektrikli kettle",
        allowed_chapters=["85"],
        source_types=["BTB"],
        min_issue_date=datetime.date(2020, 9, 8),
    )

    assert [item["btb_no"] for item in results] == ["BTB-NEW"]


def test_candidate_is_anchored_to_2026_tgtc_and_carries_all_evidence(monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setattr("api.modules.rag_engine.get_text_embedding", lambda _text: None)
    monkeypatch.setattr(
        rag_engine,
        "filter_excluded_chapters",
        lambda query_text, candidate_chapters: candidate_chapters,
    )
    monkeypatch.setattr("api.modules.rag_engine.SessionLocal", MagicMock)
    monkeypatch.setattr(
        "api.modules.rag_engine.hybrid_search_headings_and_gtip",
        lambda **_kwargs: [{
            "gtip_code": "8516.79.70.00.00",
            "description": "Elektrikli su ısıtıcıları",
            "chapter": "85",
            "heading": "8516",
            "similarity_score": 0.90,
        }],
    )
    monkeypatch.setattr(
        "api.modules.rag_engine.search_recent_customs_legislation",
        lambda **_kwargs: [{
            "reference_no": "4458/MADDE 1",
            "title": "4458 - MADDE 1",
            "publication_date": "2025-01-01",
            "excerpt": "Gümrük mevzuatı dayanağı",
            "source_url": "https://www.resmigazete.gov.tr/example",
        }],
    )

    def fake_precedent_search(*_args, source_types=None, **_kwargs):
        source_type = (source_types or ["BTB"])[0]
        return [{
            "btb_no": "BTB-2025-1" if source_type == "BTB" else "SK-2024-1",
            "source_type": source_type,
            "gtip_code": "8516.79.70.00.00",
            "chapter": "85",
            "heading": "8516",
            "issue_date": "2025-01-01",
            "product_description": "Elektrikli kettle",
            "legal_justification": "GİR 1 ve 6",
            "similarity_score": 0.88,
        }]

    monkeypatch.setattr(rag_engine.__class__.__module__ + ".local_vector_store.search_btb", fake_precedent_search)
    features = ProductFeatures(
        product_name="Elektrikli kettle",
        primary_material="Çelik",
        intended_use="Su ısıtma",
    )

    candidates = rag_engine.search_candidates(features, ["85"], ["[HARD LOCK] test"])

    assert candidates[0].gtip_code == "8516.79.70.00.00"
    assert candidates[0].precedents[0].source_type == "BTB"
    source_types = {source.source_type for source in candidates[0].legal_sources}
    assert {"TGTC_2026", "GIR", "IZAHNAME", "BTB", "SINIFLANDIRMA_KARARI", "GUMRUK_MEVZUATI"} <= source_types
    assert candidates[0].consulted_sources == CONSULTED_SOURCE_LAYERS

def test_verify_tariff_candidate_structured_output():
    """LLM verifier TariffVerification Pydantic structured output modelini doğrular."""
    from unittest.mock import MagicMock, patch

    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "candidate_gtip": "6403.59.99.00.11",
        "is_material_compliant": True,
        "is_function_compliant": True,
        "exclusion_notes_violated": False,
        "gir_rule_applied": "GIR 1",
        "legal_reasoning_points": ["Doğal deri saya ve dış taban tespit edildi."],
        "confidence_score": 0.92
    })

    with patch("api.modules.vertex_client.get_genai_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp
        mock_get_client.return_value = mock_client

        verif = llm_verifier.verify_tariff_candidate(
            raw_text="Hakiki deri erkek ayakkabısı",
            candidate_gtip="6403.59.99.00.11",
            heading_desc="Deri dış tabanlı ayakkabılar",
            chapter_notes="Fasıl 64 notları",
            gir_rules=["GIR 1"]
        )
        assert isinstance(verif, TariffVerification)
        assert verif.candidate_gtip == "6403.59.99.00.11"
        assert verif.is_material_compliant is True
        assert verif.exclusion_notes_violated is False
        assert verif.confidence_score >= 0.80

    # Fail-closed testi: Model hata verdiğinde confidence 0.0 ve MANUAL_REVIEW_REQUIRED dönmeli
    with patch("api.modules.vertex_client.get_genai_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("Vertex AI Timeout")
        mock_get_client.return_value = mock_client

        fail_verif = llm_verifier.verify_tariff_candidate(
            raw_text="Hakiki deri erkek ayakkabısı",
            candidate_gtip="6403.59.99.00.11",
            heading_desc="Deri dış tabanlı ayakkabılar",
            chapter_notes="Fasıl 64 notları",
            gir_rules=["GIR 1"]
        )
        assert isinstance(fail_verif, TariffVerification)
        assert fail_verif.confidence_score == 0.0
        assert fail_verif.is_material_compliant is False
        assert fail_verif.gir_rule_applied == "MANUAL_REVIEW_REQUIRED"

def test_hierarchical_workflow_end_to_end():
    """Uçtan uca hiyerarşik hibrit RAG ve karar motoru akışını doğrular."""
    text = "5.5 inç dokunmatik ekranlı 5G akıllı cep telefonu"
    decision = workflow_engine.start_analysis(text)
    
    assert decision is not None
    assert decision.status in ["COMPLETED", "WAITING_FOR_USER"]
    assert decision.gtip_code is not None
    assert decision.gtip_code.startswith("8517") or decision.gtip_code.startswith("85")
    assert decision.official_statute_text is not None
    assert "TGTC" in decision.official_statute_text
