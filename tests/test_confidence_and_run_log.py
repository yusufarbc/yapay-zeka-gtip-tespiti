"""Güven skoru, eşik davranışı ve karar kaydı.

Önceden her karar sabit `confidence_score=0.90` dönüyordu, `CONFIDENCE_THRESHOLD`
hiç okunmuyordu ve yalnız başarılı kararlar loglanıyordu. Bu testler skorun
yeniden sabitlenmesini ve başarısızlıkların yeniden görünmez olmasını engeller.
"""

import time

from fastapi.testclient import TestClient

from api.config import settings
from api.graph.workflow import compute_confidence, workflow_engine
from api.main import app
from api.schemas.product import PrecedentBTB


def _btb(score: float) -> PrecedentBTB:
    return PrecedentBTB(
        btb_no="TR-BTB-1",
        gtip_code="7007.19.80.00.00",
        issue_date="2025-01-01",
        product_description="Emniyet camı",
        legal_justification="GİR 1",
        similarity_score=score,
    )


def test_exact_btb_match_scores_highest():
    """Kodu model değil, idarenin birebir eşleşen kendi kararı verdi."""
    score = compute_confidence({"selection_source": "BTB_EXACT"}, [], [])
    assert score == 0.97


def test_score_is_not_a_constant():
    """Regresyon kilidi: sabit 0.90'a geri dönülmemeli."""
    weak = compute_confidence({}, [], [])
    strong = compute_confidence({"applied_gir_keys": ["GIR_1"]}, [_btb(0.95)], [])
    assert weak != strong
    assert strong > weak


def test_precedent_support_raises_confidence_proportionally():
    low = compute_confidence({}, [_btb(0.35)], [])
    high = compute_confidence({}, [_btb(0.95)], [])
    assert high > low


def test_residual_fallback_penalises_confidence():
    """Model hiçbir özel dalı eşleştiremedi; bu zayıf bir seçimdir."""
    normal = compute_confidence({"applied_gir_keys": ["GIR_1"]}, [_btb(0.6)], [])
    residual = compute_confidence(
        {"applied_gir_keys": ["GIR_1"], "used_residual_fallback": True}, [_btb(0.6)], []
    )
    assert residual < normal
    from api.graph.workflow import review_reasons
    assert review_reasons({"used_residual_fallback": True})


def test_broker_answer_raises_confidence():
    without = compute_confidence({}, [_btb(0.5)], [])
    with_answer = compute_confidence({"hitl_answer_count": 1}, [_btb(0.5)], [])
    assert with_answer > without


def test_score_stays_in_range():
    everything = {
        "applied_gir_keys": ["GIR_1", "GIR_6"],
        "hitl_answer_count": 3,
    }
    assert 0.0 <= compute_confidence(everything, [_btb(1.0)], [_btb(1.0)]) <= 0.99
    nothing = {"used_residual_fallback": True}
    assert compute_confidence(nothing, [], []) >= 0.0


def test_precedent_support_is_what_raises_the_score():
    """Skor kanıt gücünü ölçer: emsalsiz karar, emsalli karardan düşük olmalı."""
    bare = compute_confidence({}, [], [])
    supported = compute_confidence({}, [_btb(0.9)], [])
    assert supported > bare


def test_manual_review_decisions_are_also_recorded(monkeypatch):
    """
    Denetim logu yalnız COMPLETED tutuyordu; sistemin başarısız olduğu vakalar
    görünmezdi. Artık her karar `_record_run` üzerinden kaydedilir.
    """
    recorded = []
    monkeypatch.setattr(
        "api.graph.workflow._record_run",
        lambda session_id, raw_text, features, traversal, decision: recorded.append(decision.status),
    )

    decision = workflow_engine.start_analysis("ahşap sandalye")
    # Çevrimdışı ortamda katalog boş; karar manuel incelemeye düşer ama kaydedilir.
    assert decision.status in {"COMPLETED", "MANUAL_REVIEW_REQUIRED", "WAITING_FOR_USER"}
    if decision.status != "WAITING_FOR_USER":
        assert recorded, "başarısız karar kaydedilmedi"
        assert recorded[-1] == decision.status


def test_run_log_failure_never_breaks_the_decision(monkeypatch):
    """Denetim kaydı yazılamazsa kullanıcıya dönen sonuç düşmemeli."""
    def _explode(*args, **kwargs):
        raise RuntimeError("veritabanı yok")

    monkeypatch.setattr("api.db.database.SessionLocal", _explode)
    decision = workflow_engine.start_analysis("ahşap sandalye")
    assert decision.session_id


def test_correction_endpoint_requires_elevated_role():
    """Düzeltme yetkisi demo kullanıcısında olmamalı."""
    client = TestClient(app)
    response = client.post(
        "/api/v1/decisions/any-session/correct",
        json={"correct_gtip": "9401.61.00.00.11", "reason": "Yanlış fasıl"},
    )
    assert response.status_code in (401, 403)


def test_correction_rejects_malformed_code():
    client = TestClient(app)
    response = client.post(
        "/api/v1/decisions/any-session/correct",
        json={"correct_gtip": "94", "reason": "kısa kod"},
    )
    # Yetki reddi ya da geçersiz kod; hiçbir durumda 5xx olmamalı.
    assert response.status_code in (400, 401, 403, 422)


def test_chapter_backtracking_penalises_confidence():
    """
    Geri alma sonrası varılan sonuç doğru olabilir ama modelin ilk fasıl kararı
    yanlıştı. Bu zayıf bir kanıt durumudur ve otomatik onaydan uzak tutulmalı.
    """
    direct = compute_confidence({"applied_gir_keys": ["GIR_1"]}, [_btb(0.7)], [])
    backtracked = compute_confidence(
        {"applied_gir_keys": ["GIR_1"], "used_chapter_backtrack": True}, [_btb(0.7)], []
    )
    assert backtracked < direct
    # İşaret skordan BAĞIMSIZ konur: güçlü emsal varken ceza eşiği geçemiyordu.
    from api.graph.workflow import review_reasons
    assert review_reasons({"used_chapter_backtrack": True})



def test_budget_clock_starts_at_traversal_not_at_request(monkeypatch):
    """Bütçe tarife taraması içindir; öncesindeki emsal aramaları onu yememeli."""
    import api.graph.workflow as wf

    seen = {}

    def _capture(session_id, features, **kwargs):
        seen["deadline"] = kwargs.get("deadline")
        return wf.HierarchicalSearchResult(traversal_state={})

    monkeypatch.setattr(wf.GTIPWorkflowEngine, "_search", staticmethod(_capture))
    # Emsal aramasını yavaşlat: bütçe buradan sayılsaydı traversal'a süre kalmazdı.
    monkeypatch.setattr(wf.rag_engine, "search_btb_precedents",
                        lambda *a, **k: (time.sleep(0.4) or []))

    workflow_engine.start_analysis("ahşap sandalye")

    assert seen["deadline"] is not None
    remaining = seen["deadline"] - time.monotonic()
    # Gecikmeye rağmen bütçenin neredeyse tamamı traversal'a kalmalı.
    assert remaining > (settings.ANALYSIS_BUDGET_MS / 1000.0) * 0.9, (
        f"traversal'a yalnız {remaining:.1f} sn kaldı"
    )




def test_threshold_flags_weak_cases_not_every_decision():
    """
    Eşik 0.90 iken üretimdeki kararların %100'ü işaretleniyordu; her şey
    işaretlenince uyarı bilgi taşımaz. Eşik, skorun gerçekten ayırt ettiği
    zayıf kanıt durumlarını işaretlemeli.
    """
    normal = compute_confidence({"applied_gir_keys": ["GIR_1"]}, [], [])
    residual = compute_confidence(
        {"applied_gir_keys": ["GIR_1"], "used_residual_fallback": True}, [], [])
    backtracked = compute_confidence(
        {"applied_gir_keys": ["GIR_1"], "used_chapter_backtrack": True}, [], [])

    # Sıradan karar onaya takılmamalı: kullanıcı sonucu görmeli.
    assert normal >= settings.CONFIDENCE_THRESHOLD, (
        f"normal karar ({normal}) eşiğin altında — her karar işaretlenir")
    # Zayıf kanıt durumları -- skordan bağımsız olarak -- işaretlenmeli.
    from api.graph.workflow import review_reasons
    assert review_reasons({"used_residual_fallback": True})
    assert review_reasons({"used_chapter_backtrack": True})
    # Sıradan kararda hiçbir gerekçe olmamalı.
    assert review_reasons({"applied_gir_keys": ["GIR_1"]}) == []
    assert residual < normal and backtracked < normal
