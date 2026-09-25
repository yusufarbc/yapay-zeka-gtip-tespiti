"""Seçim promptuna ulaşan kanıtın doğrulanması.

Sistem her analizde BTB/EBTI emsallerini arıyor ve 96 faslın resmî notunu
yüklüyordu, fakat bunların hiçbiri seçim yapan modele ulaşmıyordu: emsaller
yalnız ekranda gösteriliyor, fasıl notları yalnız karar verildikten sonra
rapora ekleniyordu. Bu testler kanıt zincirinin sessizce kopmasını engeller.
"""

from types import SimpleNamespace

import pytest

from api.modules import llm_verifier as verifier_module
from api.modules.rag_engine import RAGEngine
from api.schemas.product import PrecedentBTB


@pytest.fixture
def captured_prompt(monkeypatch):
    """Seçiciyi gerçek çağrı yapmadan çalıştırır ve üretilen promptu yakalar."""
    box = {}

    class Models:
        def generate_content(self, **kwargs):
            box["prompt"] = kwargs["contents"]
            return SimpleNamespace(text='{"status":"SELECT","selected_candidate_id":"N1"}')

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))
    return box


def _glass_nodes():
    return [
        {"gtip_code": "7005", "description": "Float cam ve yüzeyi taşlanmış cam"},
        {"gtip_code": "7007", "description": "Emniyet camları"},
    ]


def _btb(ref: str, gtip: str, desc: str, score: float = 0.8) -> PrecedentBTB:
    return PrecedentBTB(
        btb_no=ref,
        gtip_code=gtip,
        issue_date="2025-03-10",
        product_description=desc,
        legal_justification="GİR 1 ve GİR 6 uyarınca sınıflandırılmıştır.",
        similarity_score=score,
    )


def test_relevant_precedent_reaches_the_prompt(captured_prompt):
    RAGEngine._select_node(
        "s1", "temperli cam panel", "HEADING", _glass_nodes(),
        precedents=[_btb("TR-BTB-2025-0042", "7007.19.80.00.00", "Temperli emniyet camı 8 mm")],
    )
    prompt = captured_prompt["prompt"]
    assert "TR-BTB-2025-0042" in prompt
    assert "Temperli emniyet camı 8 mm" in prompt


def test_precedent_from_another_chapter_is_filtered_out(captured_prompt):
    """Seviyeyle ilgisiz emsal prompta gürültü katmamalı — skoru yüksek olsa bile."""
    RAGEngine._select_node(
        "s1", "temperli cam panel", "HEADING", _glass_nodes(),
        precedents=[
            _btb("TR-BTB-2025-0042", "7007.19.80.00.00", "Temperli emniyet camı"),
            _btb("TR-BTB-2025-9999", "8471.30.00.00.11", "Dizüstü bilgisayar", score=0.99),
        ],
    )
    prompt = captured_prompt["prompt"]
    assert "TR-BTB-2025-0042" in prompt
    assert "TR-BTB-2025-9999" not in prompt


def test_precedents_are_marked_non_binding(captured_prompt):
    """Emsaller başka kişilere verilmiştir; model onları kural sanmamalı."""
    RAGEngine._select_node(
        "s1", "cam", "HEADING", _glass_nodes(),
        precedents=[_btb("TR-BTB-1", "7007.19.80.00.00", "Cam")],
    )
    prompt = captured_prompt["prompt"]
    assert "BAĞLAYICI DEĞİLDİR" in prompt
    assert "METİN VE NOT ÜSTÜNDÜR" in prompt


def test_chapter_notes_reach_the_prompt_below_chapter_level(captured_prompt):
    """GİR 1: sınıflandırma pozisyon metinleri VE fasıl notlarına göre yapılır."""
    RAGEngine._select_node("s1", "cam panel", "HEADING", _glass_nodes())
    prompt = captured_prompt["prompt"]
    assert "İLGİLİ FASIL NOTLARI" in prompt
    # Fasıl 70'in kendi dışlama hükmü görünür olmalı.
    assert "dahil değildir" in prompt


def test_chapter_level_omits_notes_because_all_chapters_are_options(captured_prompt):
    """97 faslın notu prompta sığmaz; CHAPTER zaten bir yönlendirme adımıdır."""
    RAGEngine._select_node(
        "s1", "cam panel", "CHAPTER",
        [{"gtip_code": "70", "description": "Cam"}, {"gtip_code": "76", "description": "Alüminyum"}],
    )
    assert "İLGİLİ FASIL NOTLARI" not in captured_prompt["prompt"]


def test_mixed_chapter_node_sets_label_each_chapter_note(captured_prompt):
    """Emsal yönlendirmesinde adaylar birden çok fasla yayılır ve fasıl seçimi
    atlanır; dışlama notları tam da bu adaylar arasında ayrım yapar. Her not
    kendi faslıyla etiketlenir ki hangi seçeneğe ait olduğu karışmasın."""
    RAGEngine._select_node(
        "s1", "cam balkon", "HEADING",
        [{"gtip_code": "7007", "description": "Emniyet camları"},
         {"gtip_code": "7610", "description": "Alüminyum inşaat aksamı"}],
    )
    prompt = captured_prompt["prompt"]
    assert "İLGİLİ FASIL NOTLARI" in prompt
    assert "FASIL 70 NOTLARI:" in prompt and "FASIL 76 NOTLARI:" in prompt


def test_retry_keeps_evidence_context(monkeypatch):
    """NO_MATCH sonrası yeniden deneme ilk denemeden daha az bilgiyle çalışmamalı."""
    prompts = []

    class Models:
        calls = 0

        def generate_content(self, **kwargs):
            Models.calls += 1
            prompts.append(kwargs["contents"])
            if Models.calls == 1:
                return SimpleNamespace(text='{"status":"NO_MATCH","selected_candidate_id":null}')
            return SimpleNamespace(text='{"status":"SELECT","selected_candidate_id":"N1"}')

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client",
                        lambda: SimpleNamespace(models=Models()))
    monkeypatch.setattr(verifier_module.time, "sleep", lambda _: None)

    verifier_module.llm_verifier.select_tariff_node(
        "cam", "HEADING", _glass_nodes(),
        precedents=[_btb("TR-BTB-KEEP", "7007.19.80.00.00", "Emniyet camı")],
        chapter_notes="FASIL 70 deneme notu",
    )

    assert len(prompts) == 2
    for prompt in prompts:
        assert "TR-BTB-KEEP" in prompt
        assert "FASIL 70 deneme notu" in prompt


def test_raw_declaration_survives_feature_extraction():
    """Ham beyan, dokuz alana damıtılırken kaybolmamalı."""
    from api.schemas.product import ProductFeatures

    features = ProductFeatures(
        product_name="Cam panel",
        primary_material="cam",
        intended_use="mimari",
    )
    text = RAGEngine._product_text(features, raw_text="8 mm temperli, 120x200 cm, kenarları rodajlı")
    assert "ORİJİNAL BEYAN: 8 mm temperli, 120x200 cm, kenarları rodajlı" in text
    # Orijinal beyan en başta olmalı: model önce ne beyan edildiğini görür.
    assert text.startswith("ORİJİNAL BEYAN:")


def test_product_text_unchanged_when_no_raw_declaration():
    from api.schemas.product import ProductFeatures

    features = ProductFeatures(
        product_name="Cam panel", primary_material="cam", intended_use="mimari",
    )
    assert not RAGEngine._product_text(features).startswith("ORİJİNAL BEYAN")


def test_ablation_flags_remove_evidence_from_the_prompt(captured_prompt, monkeypatch):
    """
    Bayraklar hem baseline ölçümünü hem de üretimde kill-switch'i mümkün kılar.

    Hepsi kapalıyken prompt, kanıt zinciri eklenmeden önceki haline döner;
    benchmark bu durumda alınan ölçümü baseline olarak kullanır.
    """
    import api.modules.rag_engine as rag_module

    for flag in ("SELECTION_USE_RAW_TEXT", "SELECTION_USE_PRECEDENTS",
                 "SELECTION_USE_CHAPTER_NOTES"):
        monkeypatch.setattr(rag_module.settings, flag, False)

    RAGEngine.search_candidates_hierarchical  # zincirin var olduğunu doğrula
    RAGEngine._select_node(
        "s1", "temperli cam panel", "HEADING", _glass_nodes(),
        precedents=[_btb("TR-BTB-2025-0042", "7007.19.80.00.00", "Emniyet camı")],
    )
    prompt = captured_prompt["prompt"]
    assert "TR-BTB-2025-0042" not in prompt
    assert "İLGİLİ FASIL NOTLARI" not in prompt
    assert "EMSAL KARARLAR" not in prompt


def test_flags_are_independent(captured_prompt, monkeypatch):
    """Tek maddenin katkısını ölçebilmek için bayraklar birbirinden bağımsız olmalı."""
    import api.modules.rag_engine as rag_module

    monkeypatch.setattr(rag_module.settings, "SELECTION_USE_PRECEDENTS", False)
    RAGEngine._select_node(
        "s1", "temperli cam panel", "HEADING", _glass_nodes(),
        precedents=[_btb("TR-BTB-2025-0042", "7007.19.80.00.00", "Emniyet camı")],
    )
    prompt = captured_prompt["prompt"]
    assert "TR-BTB-2025-0042" not in prompt      # emsaller kapalı
    assert "İLGİLİ FASIL NOTLARI" in prompt       # notlar hâlâ açık
