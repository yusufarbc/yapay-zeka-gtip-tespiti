"""NO_MATCH çıkmazından kurtarma davranışları.

120 numunelik ilk ölçümde numunelerin %35.8'i hiçbir koda bağlanamıyordu ve bu
oran kanıt zincirinden hiç etkilenmiyordu. Huni CHAPTER 120 → HEADING 83 →
SUBHEADING 67 → GTIP 46 şeklindeydi; NO_MATCH retry'larının 62'si HEADING
seviyesinde yoğunlaşıyordu. Sebep traversal'ın tek yönlü ve NO_MATCH'in ölü uç
olmasıydı. Bu testler o davranışların geri gelmesini engeller.
"""

import json
from types import SimpleNamespace

import pytest

from api.modules import llm_verifier as verifier_module
from api.modules.rag_engine import RAGEngine
from api.schemas.predicate import CandidateSelection, CandidateSelectionStatus


def _no_match(*args, **kwargs):
    return CandidateSelection(status=CandidateSelectionStatus.NO_MATCH)


def test_no_match_below_chapter_becomes_a_bounded_question(monkeypatch):
    """Model seçemediğinde sessizce pes etmek yerine resmî kardeş dalları sorar."""
    monkeypatch.setattr("api.modules.rag_engine.llm_verifier.select_tariff_node", _no_match)

    node, question, _, _ = RAGEngine._select_node(
        "s1", "belirsiz ürün", "HEADING",
        [{"gtip_code": "7007", "description": "Emniyet camları"},
         {"gtip_code": "7610", "description": "Alüminyum inşaat aksamı"}],
    )
    assert node is None
    assert question is not None
    # Soru yalnız sunucunun sahip olduğu resmî dallara bağlanmalı.
    assert set(question.target_branches.values()) >= {"7007", "7610"}


def test_official_residual_leaf_still_wins_over_asking(monkeypatch):
    """
    GTIP seviyesinde tek bir resmî 'diğerleri' dalı varsa o zaten doğru cevaptır;
    müşaviri cevabı belli bir soruyla meşgul etmek gerileme olur.
    """
    monkeypatch.setattr("api.modules.rag_engine.llm_verifier.select_tariff_node", _no_match)

    node, question, _, _ = RAGEngine._select_node(
        "s1", "kablosuz kulaklık", "GTIP",
        [{"gtip_code": "851830001000", "description": "Sivil hava taşıtlarına mahsus"},
         {"gtip_code": "851830009000", "description": "Diğerleri"}],
    )
    assert question is None
    assert node["gtip_code"] == "851830009000"


def test_chapter_level_no_match_is_not_turned_into_a_question(monkeypatch):
    """97 fasıl sorulamaz; CHAPTER bir yönlendirme seviyesidir."""
    monkeypatch.setattr("api.modules.rag_engine.llm_verifier.select_tariff_node", _no_match)

    node, question, _, _ = RAGEngine._select_node(
        "s1", "ürün", "CHAPTER",
        [{"gtip_code": "70", "description": "Cam"}, {"gtip_code": "76", "description": "Alüminyum"}],
    )
    assert node is None and question is None


def test_large_sibling_sets_are_not_dumped_into_a_question(monkeypatch):
    """Sekiz dallı bir soru müşaviri kararı kendisi vermeye zorlar."""
    monkeypatch.setattr("api.modules.rag_engine.llm_verifier.select_tariff_node", _no_match)

    nodes = [{"gtip_code": f"84{i:02d}", "description": f"Pozisyon {i}"} for i in range(8)]
    node, question, _, _ = RAGEngine._select_node("s1", "makine", "HEADING", nodes)
    assert node is None and question is None


def test_retry_after_no_match_asks_for_nearest_branches(monkeypatch):
    """
    Aynı promptu temperature=0'da tekrar göndermek deterministik kurulumda aynı
    cevabı üretir. İkinci deneme modelden en yakın dalları ister.
    """
    prompts = []

    class Models:
        calls = 0

        def generate_content(self, **kwargs):
            Models.calls += 1
            prompts.append(kwargs["contents"])
            if Models.calls == 1:
                return SimpleNamespace(text='{"status":"NO_MATCH","selected_candidate_id":null}')
            return SimpleNamespace(text=(
                '{"status":"INSUFFICIENT_INFORMATION","selected_candidate_id":null,'
                '"alternative_candidate_ids":["N1","N2"],"question_text":"Hangisi?"}'
            ))

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))
    monkeypatch.setattr(verifier_module.time, "sleep", lambda _: None)

    result = verifier_module.llm_verifier.select_tariff_node(
        "belirsiz ürün", "HEADING",
        [{"gtip_code": "7007", "description": "Emniyet camları"},
         {"gtip_code": "7610", "description": "Alüminyum aksam"}],
    )

    assert len(prompts) == 2
    assert "İKİNCİ DENEME" not in prompts[0]
    assert "İKİNCİ DENEME" in prompts[1]
    assert "EN YAKIN" in prompts[1]
    # Çıkmaz, sorulabilir bir belirsizliğe dönüşmeli.
    assert result.status == CandidateSelectionStatus.INSUFFICIENT_INFORMATION
    assert result.alternative_candidate_ids == ["N1", "N2"]


def test_narrowing_retry_changes_sampling(monkeypatch):
    """Daraltma denemesi ilk denemeyle aynı üretim ayarlarını kullanmamalı."""
    first = verifier_module.LLMFactVerifier._config(narrowing=False)
    second = verifier_module.LLMFactVerifier._config(narrowing=True)
    if first is None or second is None:
        pytest.skip("google.genai types yüklenemedi")
    assert second.temperature > first.temperature
    assert second.thinking_config.thinking_budget > first.thinking_config.thinking_budget


def test_wrong_chapter_is_retried_without_the_failed_chapter(monkeypatch):
    """
    CHAPTER seviyesinde prompt INSUFFICIENT_INFORMATION'ı yasaklar, yani model
    fasıl seçmek zorundadır. Yanlış seçerse doğru pozisyon o fasılda hiç
    bulunmaz; traversal eskiden kurtarılamıyordu.
    """
    from api.schemas.product import ProductFeatures

    seen_chapter_sets = []
    calls = {"n": 0}

    def _fake_select(session_id, product_text, level, nodes, **kwargs):
        if level == "CHAPTER":
            seen_chapter_sets.append({n["gtip_code"] for n in nodes})
            calls["n"] += 1
            # İlk denemede 70'i, ikinci denemede 76'yı seçer.
            pick = "70" if calls["n"] == 1 else "76"
            chosen = next((n for n in nodes if n["gtip_code"] == pick), nodes[0])
            return chosen, None, [], []
        if level == "HEADING":
            # Fasıl 70 altında hiçbir pozisyon eşleşmiyor (yanlış fasıl).
            if nodes and nodes[0]["gtip_code"].startswith("70"):
                return None, None, [], []
            return nodes[0], None, [], []
        return None, None, [], []

    monkeypatch.setattr(RAGEngine, "_select_node", staticmethod(_fake_select))
    monkeypatch.setattr(RAGEngine, "_chapter_nodes", staticmethod(lambda: [
        {"gtip_code": "70", "description": "Cam"},
        {"gtip_code": "76", "description": "Alüminyum"},
    ]))
    monkeypatch.setattr(RAGEngine, "_heading_nodes", staticmethod(lambda chapter: (
        [{"gtip_code": "7005", "description": "Float cam"}] if chapter == "70"
        else [{"gtip_code": "7610", "description": "Alüminyum inşaat aksamı"}]
    )))
    monkeypatch.setattr(RAGEngine, "_subheading_nodes", classmethod(lambda cls, h: []))

    result = RAGEngine().search_candidates_hierarchical(
        session_id="s1",
        features=ProductFeatures(
            product_name="cam balkon sistemi", primary_material="alüminyum", intended_use="mimari",
        ),
    )

    assert calls["n"] == 2, "fasıl seçimi yeniden denenmedi"
    # İkinci denemede başarısız fasıl seçenek kümesinden çıkarılmalı.
    assert "70" in seen_chapter_sets[0]
    assert "70" not in seen_chapter_sets[1]
    assert result.traversal_state.get("used_chapter_backtrack") is True
    assert result.traversal_state.get("locked_chapter") == "76"


def test_chapter_backtracking_is_bounded(monkeypatch):
    """Geri alma sınırsız olsaydı her başarısız ürün fasıl sayısı kadar çağrı yapardı."""
    from api.schemas.product import ProductFeatures

    calls = {"chapter": 0}

    def _always_fail_heading(session_id, product_text, level, nodes, **kwargs):
        if level == "CHAPTER":
            calls["chapter"] += 1
            return nodes[0], None, [], []
        return None, None, [], []

    monkeypatch.setattr(RAGEngine, "_select_node", staticmethod(_always_fail_heading))
    monkeypatch.setattr(RAGEngine, "_chapter_nodes", staticmethod(lambda: [
        {"gtip_code": f"{i:02d}", "description": f"Fasıl {i}"} for i in range(1, 30)
    ]))
    monkeypatch.setattr(RAGEngine, "_heading_nodes", staticmethod(lambda chapter: [
        {"gtip_code": f"{chapter}01", "description": "Pozisyon"}
    ]))

    result = RAGEngine().search_candidates_hierarchical(
        session_id="s1",
        features=ProductFeatures(product_name="x", primary_material="y", intended_use="z"),
    )
    assert calls["chapter"] == 2, f"fasıl seçimi {calls['chapter']} kez çağrıldı"
    assert result.candidates == []


def test_model_returning_too_many_alternatives_does_not_kill_the_selection(monkeypatch):
    """
    Şema alternative_candidate_ids'i 4 ile sınırlar. Kırpma CandidateSelection
    kurulduktan SONRA yapıldığı için hiç çalışmıyordu: model 11 alternatif
    döndürdüğünde ValidationError fırlıyor, seçimin tamamı düşüyor ve karar
    sessizce MANUAL_REVIEW'a gidiyordu. Canlı testte iki vaka bu yüzden kayboldu.
    """
    class Models:
        def generate_content(self, **kwargs):
            ids = [f"N{i}" for i in range(1, 12)]   # 11 alternatif
            return SimpleNamespace(text=json.dumps({
                "status": "INSUFFICIENT_INFORMATION",
                "selected_candidate_id": None,
                "alternative_candidate_ids": ids,
                "question_text": "Hangisi?",
                "reasoning_points": [f"gerekçe {i}" for i in range(12)],
                "applied_gir_keys": [f"GIR_{i}" for i in range(15)],
                "cited_chapter_notes": [str(i) for i in range(15)],
            }))

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))
    monkeypatch.setattr(verifier_module.time, "sleep", lambda _: None)

    nodes = [{"gtip_code": f"84{i:02d}", "description": f"Pozisyon {i}"} for i in range(1, 12)]
    result = verifier_module.llm_verifier.select_tariff_node("pompa", "HEADING", nodes)

    # Fazla üretim bir sözleşme ihlali değil, sapmadır: kırpılır, düşürülmez.
    assert result.status == CandidateSelectionStatus.INSUFFICIENT_INFORMATION
    assert len(result.alternative_candidate_ids) <= 4
    assert result.alternative_candidate_ids == ["N1", "N2", "N3", "N4"]


def test_oversized_lists_are_clamped_not_rejected(monkeypatch):
    """Diğer liste alanları da şema sınırını aşınca kararı düşürmemeli."""
    class Models:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text=json.dumps({
                "status": "SELECT",
                "selected_candidate_id": "N1",
                "reasoning_points": [f"r{i}" for i in range(20)],
                "applied_gir_keys": [f"GIR_{i}" for i in range(20)],
                "cited_chapter_notes": [str(i) for i in range(20)],
            }))

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))

    result = verifier_module.llm_verifier.select_tariff_node(
        "pompa", "HEADING", [{"gtip_code": "8413", "description": "Pompalar"}])

    assert result.status == CandidateSelectionStatus.SELECT
    assert result.selected_candidate_id == "N1"
    assert len(result.reasoning_points) <= 6
    assert len(result.applied_gir_keys) <= 10
    assert len(result.cited_chapter_notes) <= 10
