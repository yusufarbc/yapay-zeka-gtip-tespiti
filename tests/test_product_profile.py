"""Ürün profili ve teyit sorusu.

Müşavir geri bildirimi: "cam balkon sistemi" yazıldığında alüminyumdan hiç
bahsedilmiyordu. Profil parça bazında malzemeyi ve her bilginin kaynağını
taşır; tahmin edilen ana parça malzemesi sınıflandırma başlamadan sorulur.
"""

import os

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USE_GCP_EMULATOR", "true")

from api.modules import product_profile as pp  # noqa: E402
from api.schemas.dossier import MaterialFact, ProductDossier, ProductProfile, ProfileFact  # noqa: E402


def _model_profile(monkeypatch, data):
    monkeypatch.setattr(pp.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(pp.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(pp, "_call_model", lambda user_text, pool: data)
    monkeypatch.setattr(pp, "_material_changes_classification", lambda profile, fact, values: True)


def _cam_balkon(frame_source="INFERRED"):
    return {
        "product_type": {"value": "cam balkon sistemi", "source": "USER"},
        "function": {"value": "balkonu kapatmak", "source": "INFERRED"},
        "is_machine": False,
        "materials": [
            {"part": "taşıyıcı çerçeve", "value": "alüminyum", "source": frame_source,
             "main_part": True, "alternatives": ["PVC", "çelik"]},
            {"part": "panel", "value": "cam", "source": "USER", "main_part": True},
            {"part": "bağlantı elemanları", "value": "paslanmaz çelik", "source": "INFERRED",
             "main_part": False, "alternatives": ["galvaniz çelik"]},
        ],
    }


CAM_BALKON = _cam_balkon()


def test_inferred_main_part_material_is_asked(monkeypatch):
    _model_profile(monkeypatch, CAM_BALKON)
    question = pp.confirmation_question(pp.build_profile("cam balkon sistemi"))
    assert question["attribute"] == "material" and question["part"] == "taşıyıcı çerçeve"
    assert question["values"] == ["alüminyum", "PVC", "çelik"]
    assert "varsayıldı" in question["question_text"]


def test_user_written_material_is_not_asked(monkeypatch):
    """Model "varsayım" dese de kullanıcının yazdığı malzeme beyandır; kendisine sorulmaz."""
    _model_profile(monkeypatch, CAM_BALKON)
    profile = pp.build_profile("alüminyum doğrama cam balkon sistemi")
    frame = next(m for m in profile.materials if m.part == "taşıyıcı çerçeve")
    assert frame.source == "USER"
    assert pp.confirmation_question(profile) is None


def test_helper_parts_are_never_asked(monkeypatch):
    """Bağlantı elemanı, conta gibi yardımcı parçalar tahmin olsa da sorulmaz."""
    _model_profile(monkeypatch, _cam_balkon(frame_source="USER"))
    profile = pp.build_profile("alüminyum cam balkon sistemi")
    assert pp.confirmation_question(profile) is None
    assert not pp.has_unconfirmed_decisive_fact(profile)


def test_model_cannot_pass_a_guess_off_as_user_declaration(monkeypatch):
    """Model tahmini "kullanıcı söyledi" diye işaretlerse sunucu varsayıma indirir."""
    _model_profile(monkeypatch, _cam_balkon(frame_source="USER"))
    profile = pp.build_profile("cam balkon sistemi")
    assert next(m for m in profile.materials if m.part == "taşıyıcı çerçeve").source == "INFERRED"
    assert pp.confirmation_question(profile)["attribute"] == "material"


def test_document_source_without_attachment_is_downgraded(monkeypatch):
    _model_profile(monkeypatch, _cam_balkon(frame_source="DOCUMENT"))
    profile = pp.build_profile("cam balkon sistemi")
    assert next(m for m in profile.materials if m.part == "taşıyıcı çerçeve").source == "INFERRED"


def test_machines_are_not_asked_about_material(monkeypatch):
    _model_profile(monkeypatch, {
        "product_type": {"value": "kablosuz kulaklık", "source": "USER"},
        "is_machine": True,
        "materials": [{"part": "gövde", "value": "plastik", "source": "INFERRED", "alternatives": ["metal"]}],
    })
    assert pp.confirmation_question(pp.build_profile("kablosuz kulaklık")) is None


def test_material_is_not_asked_when_it_does_not_decide_the_classification(monkeypatch):
    """BTB ölçümünde melodika, kitap, mum gibi eşyalarda malzeme soruluyordu."""
    _model_profile(monkeypatch, {
        "product_type": {"value": "melodika", "source": "USER"},
        "is_machine": False,
        "materials": [{"part": "gövde", "value": "plastik", "source": "INFERRED", "main_part": True,
                       "alternatives": ["metal", "ahşap"]}],
    })
    monkeypatch.setattr(pp, "_material_changes_classification", lambda profile, fact, values: False)
    profile = pp.build_profile("32 tuşlu melodika")
    assert pp.confirmation_question(profile) is None
    assert not pp.has_unconfirmed_decisive_fact(profile)


def test_material_question_is_kept_when_the_check_says_it_matters(monkeypatch):
    """Kontrol "değişir" derse (cam balkon: çerçeve alüminyum mu PVC mi) soru sorulur."""
    _model_profile(monkeypatch, CAM_BALKON)
    profile = pp.build_profile("cam balkon sistemi")
    assert all(m.changes_classification for m in profile.materials)
    assert pp.confirmation_question(profile) is not None


def test_unclear_product_type_is_asked_first_and_only_one_material_question(monkeypatch):
    _model_profile(monkeypatch, {
        "product_type": {"value": "elektrik bağlantı kutusu", "source": "INFERRED"},
        "product_type_alternatives": ["buat", "sigorta kutusu"],
        "materials": [
            {"part": "gövde", "value": "plastik", "source": "INFERRED", "alternatives": ["metal"]},
            {"part": "kapak", "value": "plastik", "source": "INFERRED", "alternatives": ["cam"]},
        ],
    })
    profile = pp.build_profile("X-200")
    first = pp.confirmation_question(profile)
    assert first["attribute"] == "product_type"
    second = pp.confirmation_question(profile, skip={first["key"]})
    assert second["attribute"] == "material" and second["part"] == "gövde"
    # Bir malzeme sorusundan sonra başka malzeme sorulmaz.
    assert pp.confirmation_question(profile, skip={first["key"], second["key"]}) is None


def test_complete_declaration_skips_the_model(monkeypatch):
    monkeypatch.setattr(pp.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(pp.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(pp, "_call_model", lambda *a: (_ for _ in ()).throw(AssertionError("model çağrıldı")))
    dossier = ProductDossier(product_name="cam balkon sistemi", use_and_function="balkon kapatma", material="alüminyum")
    profile = pp.build_profile(dossier.to_raw_text(), dossier)
    assert [(m.value, m.source) for m in profile.materials] == [("alüminyum", "USER")]
    assert pp.confirmation_question(profile) is None


def test_declared_material_always_wins_over_the_model(monkeypatch):
    """Formdaki malzeme alanı açık beyandır; modelin tahminleri atılır, ayrıca sorulmaz."""
    _model_profile(monkeypatch, CAM_BALKON)
    dossier = ProductDossier(product_name="cam balkon sistemi", material="PVC", attachment_uris=["gs://b/uploads/a/foto.jpg"])
    profile = pp.build_profile(dossier.to_raw_text(), dossier)
    assert profile.materials[0].value == "PVC" and profile.materials[0].source == "USER"
    assert all(m.source != "INFERRED" for m in profile.materials)
    assert pp.confirmation_question(profile) is None


def test_model_failure_falls_back_to_the_declaration(monkeypatch):
    monkeypatch.setattr(pp.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(pp.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(pp, "_call_model", lambda *a: (_ for _ in ()).throw(TimeoutError("504")))
    profile = pp.build_profile("ahşap sandalye")
    assert [(m.value, m.source) for m in profile.materials] == [("ahşap", "USER")]
    assert any("çıkarılamadı" in note for note in profile.evidence_notes)


def test_answer_updates_the_asked_part_and_unknown_keeps_the_guess():
    profile = ProductProfile(
        product_type=ProfileFact(value="cam balkon", source="USER"),
        materials=[
            MaterialFact(part="çerçeve", value="alüminyum", source="INFERRED", alternatives=["PVC"]),
            MaterialFact(part="panel", value="cam", source="USER"),
        ],
    )
    assert pp.apply_answer(profile.model_copy(deep=True), "material", "", "çerçeve") is False
    assert pp.has_unconfirmed_decisive_fact(profile)

    assert pp.apply_answer(profile, "material", "PVC", "çerçeve") is True
    assert [(m.part, m.value, m.source) for m in profile.materials] == [
        ("çerçeve", "PVC", "BROKER"), ("panel", "cam", "USER"),
    ]
    assert not pp.has_unconfirmed_decisive_fact(profile)


def test_prompt_text_labels_every_fact_with_its_source():
    profile = ProductProfile(
        product_type=ProfileFact(value="cam balkon", source="USER"),
        materials=[MaterialFact(part="çerçeve", value="alüminyum", source="INFERRED")],
    )
    text = profile.as_prompt_text()
    assert "cam balkon (kullanıcı beyanı)" in text
    assert "çerçeve: alüminyum (model varsayımı, teyit edilmedi)" in text
    # Esas nitelik tarife hükmüdür; profil onu olgu gibi sunmaz.
    assert "ESAS NİTELİĞİ" not in text


def test_prompt_text_drops_summary_and_minor_guesses_but_keeps_function():
    """Özet cümlesi tekrar döngüsünü tetikledi; tahmini işlev ise doğruluğa katkı veriyor."""
    profile = ProductProfile(
        product_type=ProfileFact(value="cam balkon", source="USER"),
        function=ProfileFact(value="balkonu dış etkenlerden korumak", source="INFERRED"),
        use_place=ProfileFact(value="balkon", source="USER"),
        materials=[
            MaterialFact(part="çerçeve", value="alüminyum", source="INFERRED"),
            MaterialFact(part="conta", value="EPDM", source="INFERRED", main_part=False),
            MaterialFact(part="panel", value="cam", source="USER"),
        ],
        summary="Alüminyum çerçeveli cam balkon.",
    )
    text = profile.as_prompt_text()
    assert "ÖZET" not in text and "EPDM" not in text
    assert "İŞLEV: balkonu dış etkenlerden korumak (model varsayımı, teyit edilmedi)" in text
    assert "KULLANIM YERİ: balkon (kullanıcı beyanı)" in text
    assert "çerçeve: alüminyum" in text and "panel: cam" in text


# ── İş akışı: PROFILE sorusu ──────────────────────────────────────────────────

def test_workflow_asks_before_classifying_and_resumes_with_the_answer(monkeypatch):
    import api.graph.workflow as wf

    _model_profile(monkeypatch, CAM_BALKON)
    classified = {}

    def _fake_classify(self, session_id, raw_text, image_uri, features, profile, dossier, exclude, started):
        classified.update(profile=profile, features=features)
        return wf.GTIPDecision(session_id=session_id, status="COMPLETED", product_profile=profile)

    monkeypatch.setattr(wf.GTIPWorkflowEngine, "_classify", _fake_classify)

    decision = wf.workflow_engine.start_analysis("cam balkon sistemi")
    assert decision.status == "WAITING_FOR_USER"
    assert decision.state_machine_stage == "PROFILE_QUESTION"
    assert not classified, "sınıflandırma sorudan önce başlamamalı"
    options = {o.text: o.option_id for o in decision.hitl_question.options}
    assert list(options) == ["alüminyum", "PVC", "çelik", "Bilinmiyor"]

    wf.workflow_engine.resume_analysis(decision.session_id, options["alüminyum"], decision.hitl_question.question_id)
    assert classified["profile"].essential_material.source == "BROKER"
    frame = next(m for m in classified["profile"].materials if m.part == "taşıyıcı çerçeve")
    assert (frame.value, frame.source) == ("alüminyum", "BROKER")
    assert classified["features"].primary_material.startswith("alüminyum")


def test_unknown_answer_classifies_with_the_guess_and_flags_review(monkeypatch):
    import api.graph.workflow as wf

    _model_profile(monkeypatch, CAM_BALKON)
    seen = {}

    def _fake_search(session_id, features, **kwargs):
        seen["profile_text"] = kwargs.get("profile_text")
        return wf.HierarchicalSearchResult(traversal_state={})

    monkeypatch.setattr(wf.GTIPWorkflowEngine, "_search", staticmethod(_fake_search))
    monkeypatch.setattr(wf.rag_engine, "search_btb_precedents", lambda *a, **k: [])
    monkeypatch.setattr(wf.rag_engine, "search_ebti_precedents", lambda *a, **k: [])
    completed = {}
    monkeypatch.setattr(wf.GTIPWorkflowEngine, "_complete",
                        lambda self, sid, raw, img, feats, tree, *rest: (completed.setdefault("state", tree.traversal_state),
                                                                        wf.GTIPDecision(session_id=sid, status="COMPLETED"))[1])

    decision = wf.workflow_engine.start_analysis("cam balkon sistemi")
    unknown = next(o.option_id for o in decision.hitl_question.options if o.text == "Bilinmiyor")
    wf.workflow_engine.resume_analysis(decision.session_id, unknown, decision.hitl_question.question_id)

    assert "alüminyum (model varsayımı, teyit edilmedi)" in seen["profile_text"]
    assert completed["state"]["unconfirmed_profile"] is True
    assert wf.review_reasons(completed["state"])


def test_confirmation_can_be_switched_off(monkeypatch):
    import api.graph.workflow as wf

    _model_profile(monkeypatch, CAM_BALKON)
    monkeypatch.setattr(wf.settings, "PROFILE_CONFIRMATION_ENABLED", False)
    called = {}
    monkeypatch.setattr(wf.GTIPWorkflowEngine, "_classify",
                        lambda self, *a: (called.setdefault("yes", True), wf.GTIPDecision(session_id="s", status="COMPLETED"))[1])
    wf.workflow_engine.start_analysis("cam balkon sistemi")
    assert called == {"yes": True}


def test_dossier_precedent_query_ignores_field_labels():
    """Etiket kelimeleri ("EŞYA ADI", "KULLANIM") emsal eşleşmesini bozmamalı."""
    import api.graph.workflow as wf

    dossier = ProductDossier(product_name="cam balkon sistemi", use_and_function="balkon kapatma", material="alüminyum")
    assert wf.GTIPWorkflowEngine._precedent_query(dossier.to_raw_text(), dossier, None) == "cam balkon sistemi alüminyum"


def test_api_accepts_a_dossier_and_rejects_an_empty_request():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    response = client.post("/api/v1/analyze-json", json={"dossier": {
        "product_name": "ahşap sandalye", "use_and_function": "oturma, ev", "material": "ahşap",
    }})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["product_profile"]["essential_material"]["value"] == "ahşap"
    assert body["product_profile"]["essential_material"]["source"] == "USER"

    assert client.post("/api/v1/analyze-json", json={}).status_code == 422
    foreign = client.post("/api/v1/analyze-json", json={"dossier": {
        "product_name": "x ürün", "attachment_uris": ["gs://baska-bucket/dosya.jpg"]}})
    assert foreign.status_code == 422


def test_one_shared_word_does_not_make_a_guess_a_declaration(monkeypatch):
    """Canlıda tahmin edilen işlev cümlesi, yalnız "balkon" kelimesi ortak diye
    "Beyan" rozetiyle gösterildi. Kullanıcı yalnız "Cam balkon sistemi" yazmıştı."""
    _model_profile(monkeypatch, {
        **CAM_BALKON,
        "function": {"value": "Balkonları dış etkenlerden korumak ve ısı yalıtımı sağlamak", "source": "USER"},
        "use_place": {"value": "Binaların balkonlarında ve teraslarında", "source": "INFERRED"},
    })
    profile = pp.build_profile("Cam balkon sistemi")
    assert profile.function.source == "INFERRED"
    assert profile.use_place.source == "INFERRED"
    assert profile.product_type.source == "USER"
