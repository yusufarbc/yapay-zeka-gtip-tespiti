"""Emsal güdümlü pozisyon yönlendirmesi (hibrit dolaşım).

Güçlü BTB emsali olan ürünlerde dolaşım 97 fasıllık CHAPTER seçimini atlar ve
emsallerin işaret ettiği en çok 3 pozisyondan başlar. Yönlendirme yalnız bir
hızlandırıcıdır: model adaylara bağlanamazsa tam dolaşıma dönülmeli, müşavir
muhtemelen yanlış adaylar arasında seçime zorlanmamalıdır.
"""

import os
from types import SimpleNamespace

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USE_GCP_EMULATOR", "true")

import api.graph.workflow as wf  # noqa: E402
from api.config import settings  # noqa: E402
from api.modules.rag_engine import RAGEngine, route_headings_from_precedents  # noqa: E402
from api.schemas.product import ProductFeatures  # noqa: E402


def _btb(code: str, score: float, source: str = "BTB"):
    return SimpleNamespace(gtip_code=code, similarity_score=score, source_type=source)


def _features():
    return ProductFeatures(product_name="kettle", primary_material="çelik", intended_use="ev")


def test_gate_requires_a_strong_btb_precedent():
    weak = [_btb("8516.10.80.00.00", 0.79)]
    assert route_headings_from_precedents(weak, 0.80) == []

    strong = [
        _btb("8516.10.80.00.00", 0.92),
        _btb("7323.93.00.00.00", 0.60),
        _btb("8509.40.00.00.00", 0.55),
        _btb("8419.81.00.00.00", 0.50),
    ]
    assert route_headings_from_precedents(strong, 0.80, max_headings=3) == ["8516", "7323", "8509"]


def test_gate_ignores_foreign_precedents():
    """Kapı ölçümü yalnız TR BTB ile yapıldı; EBTI emsali kapıyı açmamalı."""
    ebti_only = [_btb("85161080", 0.99, source="EU_EBTI")]
    assert route_headings_from_precedents(ebti_only, 0.80) == []


def _patch_catalog(monkeypatch, selections, calls):
    def _fake_select(session_id, product_text, level, nodes, **kwargs):
        calls.append((level, [n["gtip_code"] for n in nodes], kwargs))
        return selections[level](nodes)

    monkeypatch.setattr(RAGEngine, "_select_node", staticmethod(_fake_select))
    monkeypatch.setattr("api.modules.rag_engine.get_local_tgtc_headings", lambda: {
        "8516": "Elektrikli su ısıtıcıları", "7323": "Sofra ve mutfak eşyası", "8509": "Ev tipi elektromekanik cihazlar",
    })
    monkeypatch.setattr(RAGEngine, "_heading_nodes", staticmethod(lambda chapter: [{"gtip_code": f"{chapter}01"}] * 30))
    monkeypatch.setattr(RAGEngine, "_subheading_nodes", classmethod(lambda cls, h: [{"gtip_code": f"{h}10"}]))
    monkeypatch.setattr(RAGEngine, "_leaf_nodes", staticmethod(lambda parent: [{"gtip_code": f"{parent}800000"}]))


def test_routed_traversal_skips_chapter_and_starts_at_candidates(monkeypatch):
    calls = []
    _patch_catalog(monkeypatch, {
        "HEADING": lambda nodes: (nodes[0], None, [], []),
        "SUBHEADING": lambda nodes: (nodes[0], None, [], []),
        "GTIP": lambda nodes: (nodes[0], None, [], []),
    }, calls)

    result = RAGEngine().search_candidates_hierarchical(
        session_id="s1", features=_features(), routed_headings=["8516", "7323", "9999"],
    )

    levels = [level for level, _, _ in calls]
    assert "CHAPTER" not in levels
    heading_call = calls[0]
    # Katalogda olmayan kod seçeneğe giremez.
    assert heading_call[1] == ["8516", "7323"]
    assert heading_call[2]["recover_no_match"] is False
    assert heading_call[2]["always_ask_model"] is True
    state = result.traversal_state
    assert state["routing"] == "BTB_HEADINGS"
    assert state["locked_chapter"] == "85" and state["locked_heading"] == "8516"
    assert state["locked_gtip"] == "851610800000"
    # Güven cezası faslın pozisyon sayısıyla kalibre edildi; aday sayısıyla değil.
    assert state["heading_option_count"] == 30


def test_single_routed_candidate_is_still_confirmed_by_the_model(monkeypatch):
    calls = []
    _patch_catalog(monkeypatch, {
        "HEADING": lambda nodes: (None, None, [], []),
    }, calls)

    result = RAGEngine().search_candidates_hierarchical(
        session_id="s1", features=_features(), routed_headings=["8516"],
    )

    assert calls[0][0] == "HEADING" and calls[0][1] == ["8516"]
    assert calls[0][2]["always_ask_model"] is True
    assert not result.candidates and result.discriminator_question is None
    assert result.traversal_state["routing_rejected"] is True


def test_routed_no_match_is_not_turned_into_a_question(monkeypatch):
    """NO_MATCH yönlendirmede soruya çevrilmez; çağıran tam dolaşıma döner."""
    from api.schemas.predicate import CandidateSelection, CandidateSelectionStatus

    monkeypatch.setattr(
        "api.modules.rag_engine.llm_verifier.select_tariff_node",
        lambda *a, **k: CandidateSelection(status=CandidateSelectionStatus.NO_MATCH),
    )
    nodes = [{"gtip_code": "8516", "description": "a"}, {"gtip_code": "7323", "description": "b"}]
    selected, question, _, _ = RAGEngine._select_node(
        "s", "kettle", "HEADING", nodes, recover_no_match=False,
    )
    assert selected is None and question is None
    # Varsayılan davranış korunur: tam dolaşımda aynı durum soruya çevrilir.
    _, question, _, _ = RAGEngine._select_node("s", "kettle", "HEADING", nodes)
    assert question is not None


def test_notes_for_candidates_from_several_chapters_are_all_given(monkeypatch):
    monkeypatch.setattr(
        "api.db.tgtc_knowledge_base.load_tgtc_rules_and_notes",
        lambda: {"fasil_notlari": {"85": "Bu fasla dahil değildir: ...", "73": "Not 73"}},
    )
    notes = RAGEngine._chapter_notes_for("HEADING", [{"gtip_code": "8516"}, {"gtip_code": "7323"}])
    assert "FASIL 73 NOTLARI" in notes and "FASIL 85 NOTLARI" in notes


def test_workflow_falls_back_to_full_traversal_when_routing_fails(monkeypatch):
    seen = []

    def _search(session_id, features, **kwargs):
        seen.append(kwargs.get("routed_headings"))
        return wf.HierarchicalSearchResult(traversal_state={"routing_rejected": True} if kwargs.get("routed_headings") else {})

    monkeypatch.setattr(wf.GTIPWorkflowEngine, "_search", staticmethod(_search))
    monkeypatch.setattr(wf.rag_engine, "search_btb_precedents", lambda *a, **k: [
        SimpleNamespace(
            gtip_code="8516.10.80.00.00", similarity_score=0.9, source_type="BTB",
            model_dump=lambda: {},
        ),
    ])
    monkeypatch.setattr(wf.rag_engine, "exact_btb_candidate", lambda precedents: None)
    monkeypatch.setattr(wf.rag_engine, "search_ebti_precedents", lambda *a, **k: [])

    wf.workflow_engine.start_analysis("kettle")

    assert seen == [["8516"], None], "yönlendirme başarısızken tam dolaşıma dönülmedi"


def test_routing_can_be_switched_off(monkeypatch):
    seen = []

    def _search(session_id, features, **kwargs):
        seen.append(kwargs.get("routed_headings"))
        return wf.HierarchicalSearchResult(traversal_state={})

    monkeypatch.setattr(wf.GTIPWorkflowEngine, "_search", staticmethod(_search))
    monkeypatch.setattr(wf.rag_engine, "search_btb_precedents", lambda *a, **k: [
        SimpleNamespace(gtip_code="8516.10.80.00.00", similarity_score=0.9, source_type="BTB", model_dump=lambda: {}),
    ])
    monkeypatch.setattr(wf.rag_engine, "exact_btb_candidate", lambda precedents: None)
    monkeypatch.setattr(wf.rag_engine, "search_ebti_precedents", lambda *a, **k: [])
    monkeypatch.setattr(settings, "HEADING_ROUTING_ENABLED", False)

    wf.workflow_engine.start_analysis("kettle")

    assert seen == [None]
