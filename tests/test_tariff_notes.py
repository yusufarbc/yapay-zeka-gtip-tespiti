"""Bölüm/fasıl notları ve fasıl dışlama kontrolü.

Kaynak veride bölüm notları yalnız bölümün ilk faslının metnine gömülüydü: Fasıl
76 veya 85 sınıflandırılırken Bölüm XV / XVI notları modele hiç ulaşmıyordu.
Uzun notlar düz kesiliyordu (84, 85, 72'de notun çoğu düşüyordu). Fasıl seçimi
notsuz yapıldığından yanlış fasıl ancak pozisyon seviyesinde anlaşılıyordu.
"""

import os
from types import SimpleNamespace

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USE_GCP_EMULATOR", "true")

import pytest  # noqa: E402

from api.modules import tariff_notes as tn  # noqa: E402

FAKE_NOTES = {
    "72": (
        "BÖLÜM XV\nADİ METALLER VE ADİ METALLERDEN EŞYA\nNotlar\n"
        "1. Aşağıda yazılı olanlar bu bölüme dahil değildir:\n(a) XVI. Bölüm'e giren makineler;\n"
        "2. Bu tarifede \"genel kullanımlı aksam\" tabiri şunları ifade eder: vidalar.\n"
        "FASIL 72\nDEMİR VE ÇELİK\nNotlar\n1. Bu fasılda geçen tabirler aşağıda tanımlanmıştır: pik demir.\n"
    ),
    "76": "FASIL 76\nALÜMİNYUM VE ALÜMİNYUMDAN EŞYA\nAlt Pozisyon Notları\n1. Alaşımsız alüminyum tabiri: %99.\n",
    "42": (
        "FASIL 42\nDERİ EŞYA\nNotlar\n1. Aşağıda yazılı olanlar bu fasıla dahil değildir:\n"
        "(a) 64. fasıldaki ayakkabılar;\n2. Bu fasılda başka bir hüküm de vardır.\n"
    ),
}


@pytest.fixture(autouse=True)
def _fake_notes(monkeypatch):
    monkeypatch.setattr(
        "api.db.tgtc_knowledge_base.load_tgtc_rules_and_notes",
        lambda: {"fasil_notlari": FAKE_NOTES},
    )


def test_sections_follow_the_harmonized_system_structure():
    assert tn.section_of("76") == "XV" and tn.section_of("72") == "XV" and tn.section_of("83") == "XV"
    assert tn.section_of("85") == "XVI" and tn.section_of("94") == "XX" and tn.section_of("01") == "I"


def test_section_notes_reach_every_chapter_of_the_section():
    """Bölüm XV notu yalnız Fasıl 72'nin metnindeydi; 76 da görmeli."""
    text = tn.notes_for_prompt(["76"], 9000)
    assert "BÖLÜM XV NOTLARI" in text and "XVI. Bölüm'e giren makineler" in text
    assert "FASIL 76 NOTLARI" in text and "Alaşımsız alüminyum" in text


def test_first_chapter_note_no_longer_carries_the_section_block():
    assert tn.chapter_notes("72").startswith("FASIL 72")
    assert "BÖLÜM XV" not in tn.chapter_notes("72")


def test_shared_section_note_is_given_once():
    text = tn.notes_for_prompt(["72", "76"], 9000)
    assert text.count("BÖLÜM XV NOTLARI") == 1


def test_condense_keeps_exclusions_before_other_clauses():
    long_note = "\n".join(
        [f"{i}. Genel açıklama maddesi {'x' * 300}" for i in range(1, 8)]
        + ["8. Aşağıda yazılı olanlar bu fasıla dahil değildir: (a) 64. fasıldaki ayakkabılar;"]
    )
    short = tn.condense(long_note, 900)
    assert "dahil değildir" in short
    assert "sığmayan" in short and len(short) <= 1000


def test_exclusion_clauses_only():
    text = tn.exclusion_clauses("42")
    assert "64. fasıldaki ayakkabılar" in text
    assert "başka bir hüküm" not in text


# ── Fasıl dışlama kontrolü ────────────────────────────────────────────────────

def test_fabricated_clause_does_not_exclude(monkeypatch):
    """Model hüküm metninde olmayan bir "alıntı" uydurursa dışlama sayılmaz."""
    from api.modules import llm_verifier as verifier_module

    class Models:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text='{"excluded": true, "clause": "Cam balkonlar bu fasla dahil değildir"}')

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client", lambda: SimpleNamespace(models=Models()))
    verdict = verifier_module.llm_verifier.check_chapter_exclusion(
        "cam balkon", "70", "Cam", "1. Aşağıda yazılı olanlar bu fasıla dahil değildir: (a) 32.07 pozisyonu", None,
    )
    assert verdict["excluded"] is False


def test_quoted_clause_excludes(monkeypatch):
    from api.modules import llm_verifier as verifier_module

    class Models:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text='{"excluded": true, "clause": "64. fasıldaki ayakkabılar", "redirect": "64"}')

    monkeypatch.setattr(verifier_module.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(verifier_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("api.modules.vertex_client.get_genai_client", lambda: SimpleNamespace(models=Models()))
    verdict = verifier_module.llm_verifier.check_chapter_exclusion(
        "deri ayakkabı", "42", "Deri eşya", tn.exclusion_clauses("42"), None,
    )
    assert verdict["excluded"] is True and verdict["redirect"] == "64"


def test_excluded_chapter_is_replaced_before_any_heading_call(monkeypatch):
    from api.modules.rag_engine import RAGEngine
    from api.schemas.product import ProductFeatures

    calls = []

    def _fake_select(session_id, product_text, level, nodes, **kwargs):
        calls.append((level, kwargs.get("rejected_codes"), kwargs.get("rejection_reason")))
        if level == "CHAPTER":
            pick = "64" if kwargs.get("rejected_codes") else "42"
            return {"gtip_code": pick}, None, [], []
        return (nodes[0] if nodes else None), None, [], []

    monkeypatch.setattr(RAGEngine, "_select_node", staticmethod(_fake_select))
    monkeypatch.setattr(RAGEngine, "_chapter_nodes", staticmethod(lambda: [{"gtip_code": "42"}, {"gtip_code": "64"}]))
    monkeypatch.setattr(RAGEngine, "_heading_nodes", staticmethod(lambda ch: [{"gtip_code": f"{ch}03"}]))
    monkeypatch.setattr(RAGEngine, "_subheading_nodes", classmethod(lambda cls, h: []))
    monkeypatch.setattr(RAGEngine, "_chapter_exclusion", staticmethod(
        lambda text, ch, deadline: {"excluded": ch == "42", "clause": "64. fasıldaki ayakkabılar", "redirect": "64"}
    ))

    result = RAGEngine().search_candidates_hierarchical(
        session_id="s", features=ProductFeatures(product_name="deri ayakkabı", primary_material="deri", intended_use="giyim"),
    )
    levels = [c[0] for c in calls]
    assert levels[:2] == ["CHAPTER", "CHAPTER"], "fasıl pozisyona inmeden değiştirilmeli"
    assert calls[1][1] == ["42"] and "64. fasıldaki ayakkabılar" in calls[1][2]
    assert result.traversal_state["locked_heading"] == "6403"
    assert result.traversal_state["chapter_excluded_by_note"]["chapter"] == "42"


def test_exclusion_check_can_be_switched_off(monkeypatch):
    from api.modules.rag_engine import RAGEngine, settings
    from api.schemas.product import ProductFeatures

    monkeypatch.setattr(settings, "CHAPTER_EXCLUSION_CHECK_ENABLED", False)
    monkeypatch.setattr(RAGEngine, "_chapter_exclusion", staticmethod(lambda *a: (_ for _ in ()).throw(AssertionError("çağrıldı"))))
    monkeypatch.setattr(RAGEngine, "_select_node", staticmethod(lambda s, t, level, nodes, **k: ((nodes[0] if nodes else None), None, [], [])))
    monkeypatch.setattr(RAGEngine, "_chapter_nodes", staticmethod(lambda: [{"gtip_code": "42"}]))
    monkeypatch.setattr(RAGEngine, "_heading_nodes", staticmethod(lambda ch: [{"gtip_code": f"{ch}02"}]))
    monkeypatch.setattr(RAGEngine, "_subheading_nodes", classmethod(lambda cls, h: []))
    RAGEngine().search_candidates_hierarchical(
        session_id="s", features=ProductFeatures(product_name="x", primary_material="y", intended_use="z"),
    )


def test_cited_section_note_is_listed_as_its_own_source():
    from api.db.tgtc_knowledge_base import get_official_statute_records

    sources = get_official_statute_records("761010000019", ["GIR_1"], ["76"])
    types = {s.source_type: s for s in sources}
    assert types["BOLUM_NOTU"].reference_no == "Bölüm XV Notları"
    assert "BÖLÜM XV" not in types["FASIL_NOTU"].excerpt
