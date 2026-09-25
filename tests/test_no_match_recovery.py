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
from api.modules.llm_verifier import option_id
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
                '"alternative_candidate_ids":["A","B"],"question_text":"Hangisi?"}'
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
    assert result.alternative_candidate_ids == ["A", "B"]


def test_narrowing_retry_changes_sampling(monkeypatch):
    """Daraltma denemesi ilk denemeyle aynı üretim ayarlarını kullanmamalı."""
    first = verifier_module.LLMFactVerifier._config(narrowing=False)
    second = verifier_module.LLMFactVerifier._config(narrowing=True)
    if first is None or second is None:
        pytest.skip("google.genai types yüklenemedi")
    assert second.temperature > first.temperature
    assert second.thinking_config.thinking_budget > first.thinking_config.thinking_budget


def test_backtracking_keeps_option_ids_stable_and_states_the_rejection(monkeypatch):
    """
    option_id konumsaldır (N1, N2, ...). Reddedilen dalı listeden çıkarmak tüm
    kimlikleri kaydırır: model deterministik olduğu için aynı id'yi döndürür ve
    sistem sessizce KOMŞU dala geçer. Üretim logunda tam olarak bu görüldü —
    model iki denemede de N85 dedi, sistem önce Fasıl 86'ya sonra 87'ye gitti.

    Doğru davranış: liste sabit kalır, dışlama modele açıkça bildirilir.
    """
    from api.schemas.product import ProductFeatures

    seen_chapter_sets = []
    seen_rejections = []
    calls = {"n": 0}

    def _fake_select(session_id, product_text, level, nodes, **kwargs):
        if level == "CHAPTER":
            seen_chapter_sets.append([n["gtip_code"] for n in nodes])
            seen_rejections.append(kwargs.get("rejected_codes"))
            calls["n"] += 1
            pick = "70" if calls["n"] == 1 else "76"
            chosen = next((n for n in nodes if n["gtip_code"] == pick), nodes[0])
            return chosen, None, [], []
        if level == "HEADING":
            if nodes and nodes[0]["gtip_code"].startswith("70"):
                return None, None, [], []   # yanlış fasıl: hiçbir pozisyon uymuyor
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
    # KİMLİK KARARLILIĞI: seçenek listesi iki denemede de aynı olmalı.
    assert seen_chapter_sets[0] == seen_chapter_sets[1] == ["70", "76"]
    # Dışlama modele bildirilmeli, listeden sessizce düşürülmemeli.
    assert seen_rejections[0] is None
    assert seen_rejections[1] == ["70"]
    assert result.traversal_state.get("used_chapter_backtrack") is True
    assert result.traversal_state.get("locked_chapter") == "76"


def test_reselecting_a_rejected_branch_is_refused(monkeypatch):
    """Model dışlamayı yok sayarsa seçim kapalı kabul edilmeli."""
    class Models:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text='{"status":"SELECT","selected_candidate_id":"A"}')

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))
    monkeypatch.setattr(verifier_module.time, "sleep", lambda _: None)

    result = verifier_module.llm_verifier.select_tariff_node(
        "ürün", "CHAPTER",
        [{"gtip_code": "86", "description": "Demiryolu"},
         {"gtip_code": "87", "description": "Motorlu taşıt"}],
        rejected_codes=["86"],
    )
    assert result.status == CandidateSelectionStatus.NO_MATCH


def test_rejection_is_stated_in_the_prompt(monkeypatch):
    prompts = []

    class Models:
        def generate_content(self, **kwargs):
            prompts.append(kwargs["contents"])
            return SimpleNamespace(text='{"status":"SELECT","selected_candidate_id":"B"}')

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))

    verifier_module.llm_verifier.select_tariff_node(
        "ürün", "CHAPTER",
        [{"gtip_code": "86", "description": "Demiryolu"},
         {"gtip_code": "87", "description": "Motorlu taşıt"}],
        rejected_codes=["86"],
    )
    assert "ÖNCEKİ DENEME BAŞARISIZ" in prompts[0]
    assert "86" in prompts[0]
    assert "TEKRAR SEÇME" in prompts[0]


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
            ids = [option_id(i) for i in range(11)]   # 11 alternatif
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
    assert result.alternative_candidate_ids == ["A", "B", "C", "D"]


def test_oversized_lists_are_clamped_not_rejected(monkeypatch):
    """Diğer liste alanları da şema sınırını aşınca kararı düşürmemeli."""
    class Models:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text=json.dumps({
                "status": "SELECT",
                "selected_candidate_id": "A",
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
    assert result.selected_candidate_id == "A"
    assert len(result.reasoning_points) <= 6
    assert len(result.applied_gir_keys) <= 10
    assert len(result.cited_chapter_notes) <= 10


# ---------------------------------------------------------------------------
# Seçenek kimliği / tarife kodu ayrışması
# ---------------------------------------------------------------------------

def test_option_ids_cannot_be_read_as_tariff_codes():
    """
    Kimlikler önceden N1, N2, ... idi ve fasıl kodlarıyla hizalıydı: N1..N76 tam
    olarak Fasıl 01..76'ya denk geliyor, Fasıl 77 Armonize Sistem'de ayrıldığı
    için sonrası bir kayıyordu. Model "Fasıl 85" demek isteyip N85 yazdığında
    sunucu Fasıl 86 çözüyordu — sessiz, sistematik ve en yoğun fasılları
    (84/85, korpusun %52'si) vuran bir hata.
    """
    ids = [option_id(i) for i in range(300)]
    assert ids[:3] == ["A", "B", "C"]
    assert ids[25:28] == ["Z", "AA", "AB"]
    # Hiçbir kimlik rakam içermemeli: sayısal eşleşme imkânsız olmalı.
    assert all(not any(ch.isdigit() for ch in i) for i in ids)
    assert len(set(ids)) == len(ids)


def test_chapter_option_ids_do_not_track_chapter_numbers(monkeypatch):
    """Fasıl 77 boşluğu kimlik ile kod arasında kayma yaratmamalı."""
    captured = {}

    class Models:
        def generate_content(self, **kwargs):
            captured["prompt"] = kwargs["contents"]
            return SimpleNamespace(text='{"status":"SELECT","selected_candidate_id":"A"}')

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))

    # Fasıl 77 yok: eski şemada N77 -> 78 kayması buradan başlıyordu.
    nodes = [{"gtip_code": f"{n:02d}", "description": f"Fasıl {n}"}
             for n in list(range(1, 77)) + list(range(78, 98))]
    verifier_module.llm_verifier.select_tariff_node("ürün", "CHAPTER", nodes)

    prompt = captured["prompt"]
    # Kimlik ile kodun eşleştiği hiçbir satır olmamalı.
    assert '"option_id":"A"' in prompt.replace(" ", "")
    assert "N85" not in prompt
    assert "option_id HARF kimliğidir" in prompt


# ---------------------------------------------------------------------------
# Süre bütçesi: tek tek çağrıların timeout'u vardı ama hattın bütünü için sınır
# yoktu. Bir sağlayıcı hatası (429/504) retry'larla çarpılıp dört seviyeye
# yayılınca analiz 91 saniyeye çıkabiliyordu; arayüz 45 saniyede vazgeçiyor ve
# kullanıcı hiçbir şey alamıyordu.
# ---------------------------------------------------------------------------

def test_expired_budget_skips_the_model_call_entirely(monkeypatch):
    """Bütçe dolduysa çağrı yapılmaz: kalan süre yoktur, beklemek boşunadır."""
    import time as _time

    called = {"n": 0}

    class Models:
        def generate_content(self, **kwargs):
            called["n"] += 1
            return SimpleNamespace(text='{"status":"SELECT","selected_candidate_id":"A"}')

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))

    result = verifier_module.llm_verifier.select_tariff_node(
        "ürün", "HEADING",
        [{"gtip_code": "8413", "description": "Pompalar"},
         {"gtip_code": "8414", "description": "Kompresörler"}],
        deadline=_time.monotonic() - 1,      # bütçe dolmuş
    )
    assert called["n"] == 0
    assert result.status == CandidateSelectionStatus.NO_MATCH


def test_provider_failure_uses_real_backoff_not_a_token_pause(monkeypatch):
    """429 kota hatası 0.35 saniyede düzelmez; bekleme üstel olmalı."""
    slept = []

    class Models:
        calls = 0

        def generate_content(self, **kwargs):
            Models.calls += 1
            if Models.calls == 1:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return SimpleNamespace(text='{"status":"SELECT","selected_candidate_id":"A"}')

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))
    monkeypatch.setattr(verifier_module.time, "sleep", lambda s: slept.append(s))

    verifier_module.llm_verifier.select_tariff_node(
        "ürün", "HEADING", [{"gtip_code": "8413", "description": "Pompalar"}])

    assert slept, "sağlayıcı hatasından sonra beklenmedi"
    assert slept[0] >= 1.0, f"bekleme çok kısa: {slept[0]} sn"


def test_no_retry_when_backoff_would_exhaust_the_budget(monkeypatch):
    """
    Beklemek kalan bütçeyi tüketecekse beklenmez: geriye kalan süre sonraki
    seviyeler için daha değerlidir.
    """
    import time as _time

    slept = []

    class Models:
        def generate_content(self, **kwargs):
            raise RuntimeError("504 DEADLINE_EXCEEDED")

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))
    monkeypatch.setattr(verifier_module.time, "sleep", lambda s: slept.append(s))

    result = verifier_module.llm_verifier.select_tariff_node(
        "ürün", "HEADING", [{"gtip_code": "8413", "description": "Pompalar"}],
        deadline=_time.monotonic() + 0.2,    # backoff sığmaz
    )
    assert slept == [], "bütçe yokken beklendi"
    assert result.status == CandidateSelectionStatus.NO_MATCH


def test_budget_prevents_chapter_backtracking(monkeypatch):
    """Geri alma ikinci bir fasıl+pozisyon turu demektir; bütçe yoksa yapılmaz."""
    import time as _time

    from api.schemas.product import ProductFeatures

    calls = {"chapter": 0}

    def _fake_select(session_id, product_text, level, nodes, **kwargs):
        if level == "CHAPTER":
            calls["chapter"] += 1
            return nodes[0], None, [], []
        return None, None, [], []

    monkeypatch.setattr(RAGEngine, "_select_node", staticmethod(_fake_select))
    monkeypatch.setattr(RAGEngine, "_chapter_nodes", staticmethod(lambda: [
        {"gtip_code": "70", "description": "Cam"},
        {"gtip_code": "76", "description": "Alüminyum"},
    ]))
    monkeypatch.setattr(RAGEngine, "_heading_nodes", staticmethod(
        lambda chapter: [{"gtip_code": f"{chapter}05", "description": "Pozisyon"}]))

    RAGEngine().search_candidates_hierarchical(
        session_id="s1",
        features=ProductFeatures(product_name="x", primary_material="y", intended_use="z"),
        deadline=_time.monotonic() - 1,      # bütçe dolmuş
    )
    assert calls["chapter"] == 1, "bütçe yokken geri alma yapıldı"


def test_call_timeout_scales_with_remaining_budget():
    """
    Sabit timeout, tek bir yavaş çağrının bütçenin tamamını yemesine izin
    veriyordu: CHAPTER'da iki kez 504 alınca alt seviyeler hiç denenmiyordu.
    """
    import time as _time

    cfg = verifier_module.LLMFactVerifier
    ceiling = verifier_module.settings.LLM_TIMEOUT_MS

    # Bütçe bol: tavan uygulanır
    assert cfg._call_timeout_ms(_time.monotonic() + 60) == ceiling
    # Bütçe daralınca timeout da daralır
    tight = cfg._call_timeout_ms(_time.monotonic() + 10)
    assert tight < ceiling
    # Kalan sürenin TAMAMI verilmez: sonraki seviyelere pay kalmalı
    assert tight < 10_000
    # Taban altına inilmez: 4 sn'den kısası hiçbir çağrıya yetmez
    assert cfg._call_timeout_ms(_time.monotonic() + 0.1) == 4000
    # Bütçe yoksa davranış değişmez
    assert cfg._call_timeout_ms(None) == ceiling


def test_call_timeout_reaches_the_provider_config():
    cfg = verifier_module.LLMFactVerifier._config(timeout_ms=7000)
    if cfg is None:
        import pytest as _pytest
        _pytest.skip("google.genai types yüklenemedi")
    assert cfg.http_options.timeout == 7000


def test_chapter_heading_labels_are_tunable(monkeypatch):
    """
    CHAPTER promptu 900 karakterlik kapsam özetiyle ~17.500 token oluyordu ve
    hattın 504 alan en yavaş çağrısı buydu. Uzunluk env ile ayarlanabilir ki
    hız/doğruluk dengesi yeniden deploy etmeden değiştirilebilsin.
    """
    import api.modules.rag_engine as rag_module

    monkeypatch.setattr(rag_module.settings, "CHAPTER_HEADING_LABEL_CHARS", 55)
    long_nodes = RAGEngine._chapter_nodes()
    long_size = sum(len(n["description"]) for n in long_nodes)

    monkeypatch.setattr(rag_module.settings, "CHAPTER_HEADING_LABEL_CHARS", 20)
    short_nodes = RAGEngine._chapter_nodes()
    short_size = sum(len(n["description"]) for n in short_nodes)

    assert short_size < long_size
    # Fasıl kümesi değişmemeli: yalnız açıklama kısalır.
    assert [n["gtip_code"] for n in short_nodes] == [n["gtip_code"] for n in long_nodes]
    # Fasıl başlığı her durumda korunur; onsuz seçim yapılamaz.
    assert all(n["description"].strip() for n in short_nodes)


def test_zero_label_length_keeps_heading_codes(monkeypatch):
    """Kapsam tamamen kapatılsa bile fasıl başlığı kalmalı."""
    import api.modules.rag_engine as rag_module

    monkeypatch.setattr(rag_module.settings, "CHAPTER_HEADING_LABEL_CHARS", 0)
    nodes = RAGEngine._chapter_nodes()
    assert all(n["description"].strip() for n in nodes)
    # Etiket kapatılsa bile pozisyon KODLARI kalır: liste asla kesilmez.
    ch61 = next(n for n in nodes if n["gtip_code"] == "61")
    assert "6109" in ch61["description"]


def test_first_chapter_no_match_backtracks_before_narrowing(monkeypatch):
    """Canlıda: ahşap sandalye -> Fasıl 44, pozisyonların hiçbiri uymadı. Daraltma
    denemesi yanlış fasılda "en yakın" 4419'u seçtirip dolaşımı yanlış dala soktu.
    Geri alma hakkı varken önce fasıl geri alınmalı; daraltma ve soru son fasla kalır."""
    from api.schemas.product import ProductFeatures

    calls = []

    def _selector(product_text, level, nodes, **kwargs):
        calls.append((level, [n["gtip_code"] for n in nodes], kwargs.get("_no_match_retries"), kwargs.get("rejected_codes")))
        if level == "CHAPTER":
            pick = "B" if kwargs.get("rejected_codes") else "A"
            return CandidateSelection(status=CandidateSelectionStatus.SELECT, selected_candidate_id=pick)
        if nodes[0]["gtip_code"].startswith("44"):
            return CandidateSelection(status=CandidateSelectionStatus.NO_MATCH)
        return CandidateSelection(status=CandidateSelectionStatus.SELECT, selected_candidate_id="A")

    monkeypatch.setattr("api.modules.rag_engine.llm_verifier.select_tariff_node", _selector)
    monkeypatch.setattr(RAGEngine, "_chapter_nodes", staticmethod(lambda: [
        {"gtip_code": "44", "description": "Ahşap eşya"},
        {"gtip_code": "94", "description": "Mobilya"},
    ]))
    monkeypatch.setattr(RAGEngine, "_heading_nodes", staticmethod(lambda chapter: [
        {"gtip_code": f"{chapter}01", "description": "a"},
        {"gtip_code": f"{chapter}02", "description": "b"},
    ]))
    monkeypatch.setattr(RAGEngine, "_subheading_nodes", classmethod(lambda cls, h: []))

    result = RAGEngine().search_candidates_hierarchical(
        session_id="s1",
        features=ProductFeatures(product_name="ahşap sandalye", primary_material="ahşap", intended_use="oturma"),
    )

    first_heading = next(c for c in calls if c[0] == "HEADING")
    assert first_heading[1] == ["4401", "4402"]
    assert first_heading[2] == 0, "ilk fasılda daraltma denemesi yapılmamalı"
    assert result.discriminator_question is None, "yanlış faslın pozisyonları sorulmamalı"
    assert result.traversal_state["used_chapter_backtrack"] is True
    assert result.traversal_state["locked_heading"] == "9401"
    second_heading = [c for c in calls if c[0] == "HEADING"][1]
    assert second_heading[2] is None, "son fasılda varsayılan kurtarma geçerli olmalı"


def test_rejection_names_the_option_id_and_reselection_is_retried(monkeypatch):
    """Model harf kimliğiyle seçer; uyarı yalnız "44" deyince yine "AR" seçiliyordu.
    Reddedilen dal yeniden seçilirse doğrudan pes edilmez, bir kez daha sorulur."""
    prompts = []
    answers = iter(['{"status":"SELECT","selected_candidate_id":"A"}',
                    '{"status":"SELECT","selected_candidate_id":"B"}'])

    class Models:
        def generate_content(self, **kwargs):
            prompts.append(kwargs["contents"])
            return SimpleNamespace(text=next(answers))

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client", lambda: SimpleNamespace(models=Models()))
    monkeypatch.setattr(verifier_module.time, "sleep", lambda _: None)

    selection = verifier_module.llm_verifier.select_tariff_node(
        "ahşap sandalye", "CHAPTER",
        [{"gtip_code": "44", "description": "Ahşap eşya"}, {"gtip_code": "94", "description": "Mobilya"}],
        rejected_codes=["44"],
    )
    assert "A (44)" in prompts[0]
    assert len(prompts) == 2, "reddedilen dal yeniden seçilince tekrar sorulmadı"
    assert selection.selected_candidate_id == "B"
