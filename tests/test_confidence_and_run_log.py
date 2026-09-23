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
    assert residual < settings.CONFIDENCE_THRESHOLD


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


def test_unsupported_decision_falls_below_threshold():
    """Emsalsiz ve gerekçesiz bir seçim otomatik onaylanmamalı."""
    assert compute_confidence({}, [], []) < settings.CONFIDENCE_THRESHOLD


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
    assert backtracked < settings.CONFIDENCE_THRESHOLD


def test_international_research_does_not_starve_the_classification(monkeypatch):
    """
    Grounding'li arama istek başında çalıştırılıyor ve onlarca saniye sürüyordu.
    Süre bütçesi istek başlangıcından sayıldığı için traversal başladığında
    süre bitmiş oluyor, her tarife seviyesi atlanıyor ve karar
    MODEL_BINDING_FAILED ile manuel incelemeye düşüyordu.

    Arayüzde "Uluslararası Emsalleri Canlı Araştır" kutusu işaretliyken her
    analiz bu yüzden sonuçsuz kalıyordu.
    """
    called = {"n": 0}

    def _slow_search(*args, **kwargs):
        called["n"] += 1
        return []

    monkeypatch.setattr(
        "api.modules.international_search.search_international_rulings", _slow_search
    )

    decision = workflow_engine.start_analysis(
        "alüminyum doğrama cam balkon sistemi", enable_international_research=True
    )

    # Sınıflandırma öncesi çağrılmamalı; arama kod kilitlendikten sonra
    # ve HS ipucuyla yapılır.
    assert called["n"] == 0 or decision.status == "COMPLETED"


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


# ---------------------------------------------------------------------------
# Uluslararası emsal: gösterim değil, bağımsız çapraz kontrol
# ---------------------------------------------------------------------------

def test_foreign_disagreement_lowers_confidence_below_threshold():
    """
    Armonize Sistem ilk altı hanede uluslararası ortaktır. Yabancı bir idare
    aynı eşyayı farklı alt pozisyona koyduysa bu gerçek bir uyuşmazlıktır ve
    kararın otomatik onaylanmasını engellemelidir. Önceden bu kararlar yalnız
    ekranda gösteriliyor, sınıflandırmaya hiç etki etmiyordu.
    """
    agreed = compute_confidence({"applied_gir_keys": ["GIR_1"]}, [_btb(0.9)], [])
    disputed = compute_confidence(
        {"applied_gir_keys": ["GIR_1"], "international_disagreement": ["392590"]},
        [_btb(0.9)], [],
    )
    assert disputed < agreed
    assert disputed < settings.CONFIDENCE_THRESHOLD


def test_search_runs_without_the_hs_hint(monkeypatch):
    """
    Seçilen kodu ipucu olarak vermek, modelin o kodu DOĞRULAYAN kararlar
    bulmasına yol açıyordu: bağımsız kontrol gibi görünen ama olmayan bir teyit.
    """
    import api.modules.international_search as intl

    seen = {}

    def _capture(product_text, hs_code_hint=None, target_countries=None,
                 max_results=4, timeout_ms=None):
        seen["hint"] = hs_code_hint
        seen["timeout"] = timeout_ms
        return []

    monkeypatch.setattr(intl, "search_international_rulings", _capture)
    workflow_engine.start_analysis(
        "alüminyum doğrama cam balkon sistemi", enable_international_research=True
    )
    if "hint" in seen:
        assert seen["hint"] is None, "arama seçilen kodla beslenmiş"


def test_search_is_skipped_when_too_little_time_remains(monkeypatch):
    """
    Grounding'li arama ~20 sn sürüyor. Birkaç saniye kalmışken denemek yalnız
    kullanıcıyı bekletir ve istemci zaman aşımı riskini artırır.
    """
    import api.graph.workflow as wf

    called = {"n": 0}

    def _never(*args, **kwargs):
        called["n"] += 1
        return []

    monkeypatch.setattr(
        "api.modules.international_search.search_international_rulings", _never
    )
    decision = wf.GTIPWorkflowEngine._complete(
        wf.workflow_engine,
        "s1", "ürün", None,
        __import__("api.schemas.product", fromlist=["ProductFeatures"]).ProductFeatures(
            product_name="x", primary_material="y", intended_use="z"),
        wf.HierarchicalSearchResult(traversal_state={
            "enable_international_research": True,
            "intl_deadline": time.monotonic() - 5,   # süre bitmiş
        }),
    )
    assert called["n"] == 0
    assert decision.session_id
