"""
Unit & Integration Tests for Hierarchical Hybrid RAG, pgvector database functions,
Chapter Exclusion Verification, and Structured Tariff Verification.
"""

import pytest
from api.schemas.product import ProductFeatures, GTIPCandidate
from api.schemas.predicate import TariffVerification, ChapterExclusionCheck
from api.modules.rag_engine import rag_engine
from api.modules.llm_verifier import llm_verifier
from api.graph.workflow import workflow_engine
from api.db.database import (
    SessionLocal, compute_rrf_score, hybrid_search_headings_and_gtip,
    search_chapter_notes_and_exclusions
)

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

def test_verify_tariff_candidate_structured_output():
    """LLM verifier TariffVerification Pydantic structured output modelini doğrular."""
    verif = llm_verifier.verify_tariff_candidate(
        raw_text="Hakiki deri erkek ayakkabısı",
        candidate_gtip="6403.59.99.00.11",
        heading_desc="Deri dış tabanlı ayakkabılar",
        chapter_notes="Fasıl 64 notları",
        gir_rules=["GIR 1"]
    )
    assert isinstance(verif, TariffVerification)
    assert verif.candidate_gtip == "6403.59.99.00.11"
    assert verif.is_material_compliant == True
    assert verif.exclusion_notes_violated == False
    assert verif.confidence_score >= 0.80

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
