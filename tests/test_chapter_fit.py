"""Pozisyon sorusu sorulmadan önce fasıl uygunluk kontrolü.

Canlıda "cam balkon" önce Fasıl 70'e (cam) gidiyor ve pozisyon seviyesinde
"float cam mı, temperli cam mı?" soruluyordu: müşavir yanlış fasılda yanlış
seçenekler arasında seçime zorlanıyordu. Soru gösterilmeden önce fasıl
sorgulanır; ürün faslın pozisyonlarına girmiyorsa fasıl geri alınır.
"""

import os

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USE_GCP_EMULATOR", "true")

from api.modules.discriminator_engine import DiscriminatorQuestion  # noqa: E402
from api.modules.rag_engine import RAGEngine, settings  # noqa: E402
from api.schemas.product import ProductFeatures  # noqa: E402


def _question(session_id="s"):
    return DiscriminatorQuestion(
        session_id=session_id, parameter_name="p", question_text="Float mı, temperli mi?",
        options=["7005 — float", "7007 — emniyet camı", "Bilinmiyor"],
        target_branches={"0": "7005", "1": "7007", "2": ""},
    )


def _setup(monkeypatch, fit_belongs, calls, locked_chapter_source="model"):
    def _fake_select(session_id, product_text, level, nodes, **kwargs):
        calls.append((level, [n["gtip_code"] for n in nodes], kwargs.get("rejected_codes"), kwargs.get("rejection_reason")))
        if level == "CHAPTER":
            return {"gtip_code": "76" if kwargs.get("rejected_codes") else "70"}, None, [], []
        if level == "HEADING" and nodes[0]["gtip_code"].startswith("70"):
            return None, _question(session_id), [], []
        return (nodes[0] if nodes else None), None, [], []

    monkeypatch.setattr(RAGEngine, "_select_node", staticmethod(_fake_select))
    monkeypatch.setattr(RAGEngine, "_chapter_nodes", staticmethod(lambda: [{"gtip_code": "70"}, {"gtip_code": "76"}]))
    monkeypatch.setattr(RAGEngine, "_heading_nodes", staticmethod(lambda ch: [
        {"gtip_code": f"{ch}05", "description": "a"}, {"gtip_code": f"{ch}10", "description": "b"},
    ]))
    monkeypatch.setattr(RAGEngine, "_subheading_nodes", classmethod(lambda cls, h: []))
    monkeypatch.setattr(RAGEngine, "_chapter_exclusion", staticmethod(lambda *a: {"excluded": False}))
    fit_calls = []
    monkeypatch.setattr(
        "api.modules.rag_engine.llm_verifier.confirm_chapter_fit",
        lambda text, ch, title, headings, deadline: (fit_calls.append(ch), {
            "belongs": fit_belongs, "reason": "Pozisyonlar yalnız cam paneli tanımlıyor; taşıyıcı alüminyum", "better_chapter": "76",
        })[1],
    )
    return fit_calls


def _features():
    return ProductFeatures(product_name="cam balkon sistemi", primary_material="alüminyum / cam", intended_use="balkon")


def test_wrong_chapter_is_backtracked_instead_of_asking(monkeypatch):
    calls = []
    fit_calls = _setup(monkeypatch, fit_belongs=False, calls=calls)
    result = RAGEngine().search_candidates_hierarchical(session_id="s", features=_features())

    assert fit_calls == ["70"]
    assert result.discriminator_question is None, "yanlış fasılda soru sorulmamalı"
    second_chapter = [c for c in calls if c[0] == "CHAPTER"][1]
    assert second_chapter[2] == ["70"] and "taşıyıcı alüminyum" in second_chapter[3]
    assert result.traversal_state["locked_heading"] == "7605"
    assert result.traversal_state["chapter_fit_rejected"]["chapter"] == "70"


def test_question_is_kept_when_the_chapter_fits(monkeypatch):
    calls = []
    fit_calls = _setup(monkeypatch, fit_belongs=True, calls=calls)
    result = RAGEngine().search_candidates_hierarchical(session_id="s", features=_features())

    assert fit_calls == ["70"]
    assert result.discriminator_question is not None
    assert result.traversal_state["pending_level"] == "HEADING"


def test_broker_chosen_chapter_is_never_questioned(monkeypatch):
    """Müşavir faslı seçtiyse (HITL devamı) uygunluk kontrolü yapılmaz."""
    calls = []
    fit_calls = _setup(monkeypatch, fit_belongs=False, calls=calls)
    result = RAGEngine().search_candidates_hierarchical(
        session_id="s", features=_features(), locked_chapter="70",
    )
    assert fit_calls == []
    assert result.discriminator_question is not None


def test_fit_check_can_be_switched_off(monkeypatch):
    calls = []
    fit_calls = _setup(monkeypatch, fit_belongs=False, calls=calls)
    monkeypatch.setattr(settings, "CHAPTER_FIT_CHECK_ENABLED", False)
    result = RAGEngine().search_candidates_hierarchical(session_id="s", features=_features())
    assert fit_calls == []
    assert result.discriminator_question is not None
