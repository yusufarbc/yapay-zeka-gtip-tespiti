"""Kararın seviye seviye gerekçesi ("Neden bu kod?").

Sonuç ekranı yalnız bu izi gösterir: hangi resmî dal, neden seçildi. Önceden
modelin yazdığı gerekçe hiç saklanmıyor, ekranda sabit bir cümle çıkıyordu.
"""

import os

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USE_GCP_EMULATOR", "true")

from api.graph.workflow import rationale_commentary, selection_rationale  # noqa: E402
from api.modules.rag_engine import RAGEngine, record_selection_step  # noqa: E402
from api.schemas.predicate import CandidateSelection, CandidateSelectionStatus  # noqa: E402


def test_model_reasoning_is_kept_with_the_selected_official_branch(monkeypatch):
    monkeypatch.setattr(
        "api.modules.rag_engine.llm_verifier.select_tariff_node",
        lambda *a, **k: CandidateSelection(
            status=CandidateSelectionStatus.SELECT,
            selected_candidate_id="B",
            reasoning_points=["Alüminyum profil taşıyıcıdır; GİR 3(b) uyarınca esas niteliği verir."],
            applied_gir_keys=["GIR_3B"],
            cited_chapter_notes=["70"],
        ),
    )
    traversal = {}
    RAGEngine._select_node(
        "s", "cam balkon", "HEADING",
        [{"gtip_code": "7007", "description": "Emniyet camları"},
         {"gtip_code": "7610", "description": "Alüminyum inşaat aksamı"}],
        traversal=traversal,
    )
    step = traversal["selection_trail"][0]
    assert step["code"] == "7610" and step["source"] == "MODEL"
    assert "GİR 3(b)" in step["reasoning_points"][0]
    assert step["applied_gir_keys"] == ["GIR_3B"] and step["cited_chapter_notes"] == ["70"]


def test_single_option_is_marked_as_such():
    traversal = {}
    RAGEngine._select_node("s", "x", "SUBHEADING", [{"gtip_code": "761010", "description": "Kapılar"}], traversal=traversal)
    assert traversal["selection_trail"][0]["source"] == "SINGLE_OPTION"


def test_reselecting_a_level_drops_the_abandoned_path():
    """Fasıl geri alındığında reddedilen faslın adımları izde kalmamalı."""
    traversal = {}
    record_selection_step(traversal, "CHAPTER", {"gtip_code": "70"}, "MODEL", ["cam"])
    record_selection_step(traversal, "HEADING", {"gtip_code": "7005"}, "MODEL", ["float"])
    record_selection_step(traversal, "CHAPTER", {"gtip_code": "76"}, "MODEL", ["alüminyum"])
    assert [step["code"] for step in traversal["selection_trail"]] == ["76"]


def test_exact_btb_decision_explains_its_source():
    from types import SimpleNamespace

    steps = selection_rationale(
        {"selection_source": "BTB_EXACT", "locked_gtip": "761010000019"},
        [SimpleNamespace(btb_no="TR-2025-1", similarity_score=1.0)],
    )
    assert steps[0].source == "BTB_EXACT" and "TR-2025-1" in steps[0].reasoning_points[0]


def test_commentary_is_built_from_the_trail():
    traversal = {}
    record_selection_step(traversal, "CHAPTER", {"gtip_code": "76"}, "MODEL", ["Alüminyum eşya."])
    record_selection_step(traversal, "SUBHEADING", {"gtip_code": "761010"}, "BROKER")
    text = rationale_commentary(selection_rationale(traversal, []))
    assert "Fasıl 76: Alüminyum eşya." in text
    assert "Alt pozisyon 761010: Müşavir seçti." in text


def test_completed_decision_carries_rationale_and_evidence_summary():
    from api.graph.workflow import workflow_engine

    decision = workflow_engine.start_analysis("ahşap sandalye")
    if decision.status == "COMPLETED":
        assert decision.selection_rationale, "karar gerekçe izi taşımıyor"
        assert decision.evidence_summary
        assert decision.llm_reasoning_commentary


def test_resume_puts_the_broker_choice_between_earlier_and_later_steps(monkeypatch):
    import api.graph.workflow as wf
    from api.db.gcp_emulator import local_state_store

    local_state_store.save_state("rationale-s1", {
        "session_id": "rationale-s1",
        "raw_text": "cam balkon",
        "product_features": {"product_name": "cam balkon", "primary_material": "alüminyum", "intended_use": "mimari"},
        "status": "WAITING_FOR_USER",
        "hitl_question": {
            "question_id": "q1",
            "options": [{"option_id": "DISC_0", "text": "7610 — Alüminyum inşaat aksamı",
                         "impact_data": {"selected_branch": "7610"}}],
        },
        "discriminator_traversal": {
            "pending_level": "HEADING",
            "locked_chapter": "76",
            "selection_trail": [{"level": "CHAPTER", "code": "76", "description": "Alüminyum", "source": "MODEL",
                                 "reasoning_points": ["Alüminyum eşya."]}],
        },
    })
    later = {"level": "SUBHEADING", "code": "761010", "description": "Kapılar", "source": "MODEL",
             "reasoning_points": ["Sürme kapı sistemi."]}
    monkeypatch.setattr(wf.GTIPWorkflowEngine, "_search", staticmethod(
        lambda *a, **k: wf.HierarchicalSearchResult(traversal_state={"selection_trail": [later]})
    ))
    captured = {}
    monkeypatch.setattr(wf.GTIPWorkflowEngine, "_complete",
                        lambda self, sid, raw, img, feats, tree: captured.setdefault("trail", tree.traversal_state["selection_trail"]))

    wf.workflow_engine.resume_analysis("rationale-s1", "DISC_0", "q1")

    trail = captured["trail"]
    assert [(s["level"], s["source"]) for s in trail] == [
        ("CHAPTER", "MODEL"), ("HEADING", "BROKER"), ("SUBHEADING", "MODEL"),
    ]
    assert trail[1]["code"] == "7610" and trail[1]["description"] == "Alüminyum inşaat aksamı"


def test_displayed_branch_text_drops_model_only_scope_and_indent_dashes():
    from api.modules.rag_engine import _display_description

    assert _display_description("Fasıl 76: Alüminyum. Pozisyon kapsamı: 7601: ham") == "Fasıl 76: Alüminyum"
    assert _display_description("- Diğer pompalar: > - - Diğerleri") == "Diğer pompalar: > Diğerleri"
