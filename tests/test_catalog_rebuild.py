"""TGTC kataloğunun hiyerarşiyle yeniden çıkarımı.

Mevcut katalog, ham cetvelde kod sütunu boş olan iki satır türünü atmıştı:
ara grup başlıkları (ayrımı taşıyanlar) ve satır sarması devamları. Sonuçta
15718 yaprağın 3645'i kardeşiyle özdeş metne sahipti; `841370` altında 22
yaprağın tamamı aynı şeyi yazıyordu.

Bu testler ayrıştırma mantığını veritabanı ve Excel gerektirmeden doğrular.
"""

import pytest

from scripts.rebuild_tgtc_catalog import build_full_path, dash_depth, strip_dashes


def _entry(depth, own_text, ancestors):
    return {
        "depth": depth,
        "own_text": own_text,
        "ancestor_depths": sorted(ancestors),
        "ancestors_snapshot": dict(ancestors),
    }


def test_dash_depth_reads_tariff_hierarchy_level():
    assert dash_depth("- Diğer santrifüj pompalar:") == 1
    assert dash_depth("- - Dalgıç pompaları:") == 2
    assert dash_depth("- - - - Diğerleri") == 4
    assert dash_depth("- - - - - - - - Diğerleri") == 8
    # Kodlu ama dashsız satır: fasıl/pozisyon başlığı
    assert dash_depth("Sıvılar için pompalar") == 0


def test_strip_dashes_keeps_only_discriminating_text():
    assert strip_dashes("- - - - Diğerleri") == "Diğerleri"
    assert strip_dashes("- - -Sivil hava taşıtları") == "Sivil hava taşıtları"


def test_full_path_makes_identical_siblings_distinguishable():
    """
    Ayrımı ara başlıklar taşır. Onlar olmadan iki kardeş de "Diğerleri" der.
    """
    first = _entry(4, "Diğerleri", {1: "Diğer santrifüj pompalar:",
                                    2: "Dalgıç pompaları:", 3: "Tek kademeli olanlar"})
    second = _entry(4, "Diğerleri", {1: "Diğer santrifüj pompalar:",
                                     2: "Dalgıç pompaları:", 3: "Çok kademeli olanlar"})
    path_a, path_b = build_full_path(first), build_full_path(second)

    assert path_a != path_b
    assert "Tek kademeli olanlar" in path_a
    assert "Çok kademeli olanlar" in path_b


def test_consecutive_repeats_are_collapsed():
    """'Diğerleri > Diğerleri' bilgi taşımaz, yalnız yolu uzatır."""
    entry = _entry(3, "Diğerleri", {1: "Diğerleri:", 2: "Diğerleri:"})
    assert build_full_path(entry) == "Diğerleri"


def test_non_consecutive_repeats_are_kept():
    """Aynı kelime farklı seviyelerde ayrım taşıyabilir; körlemesine silinmez."""
    entry = _entry(3, "Diğerleri", {1: "Diğerleri:", 2: "Çıkış ağzı çapı 15 mm.yi geçenler:"})
    path = build_full_path(entry)
    assert path.startswith("Diğerleri > Çıkış ağzı")
    assert path.endswith("Diğerleri")


def test_truncation_drops_ancestors_not_the_discriminating_tail():
    """
    Ayırt edici metin daima en sondadır. Sondan kesmek balık türü gibi uzun
    dallarda kardeşleri yeniden özdeş hale getiriyordu.
    """
    long_ancestor = "A" * 400
    entry = _entry(3, "Avrupa sardalya balığı türü sardalyalar (Sardina pilchardus)",
                   {1: long_ancestor, 2: "B" * 400})
    path = build_full_path(entry, max_chars=200)

    assert len(path) <= 200
    assert path.endswith("Avrupa sardalya balığı türü sardalyalar (Sardina pilchardus)")
    assert long_ancestor not in path


def test_single_oversized_level_keeps_its_tail():
    entry = _entry(1, "X" * 300 + "AYIRT_EDICI", {})
    path = build_full_path(entry, max_chars=50)
    assert len(path) <= 50
    assert path.endswith("AYIRT_EDICI")


def test_rebuild_matches_the_live_catalog_code_set():
    """
    Yetkili katalogda kod kaybı her kararın reddedilmesine yol açar:
    validate_leaf_gtip bilinmeyen kodu fail-closed ile geri çevirir.
    """
    pytest.importorskip("pandas")
    import os

    from scripts.rebuild_tgtc_catalog import SOURCE_DIR, load_current, rebuild

    if not os.path.isdir(SOURCE_DIR):
        pytest.skip("Ham TGTC Excel dizini yok (container/CI ortamı)")

    rebuilt = {r["gtip_code"] for r in rebuild() if len(r["gtip_code"]) == 12}
    current = {c for c in load_current() if len(c) == 12}

    assert rebuilt == current, (
        f"kod kümesi değişti: kayıp={len(current - rebuilt)} eklenen={len(rebuilt - current)}"
    )


# ---------------------------------------------------------------------------
# Ortak önek ayıklama: açıklamalar tam yol taşıdığından kardeşler baş kısmı
# paylaşır. O kısım seçimi belirlemez, yalnız ayrımı gömer ve token harcar.
# ---------------------------------------------------------------------------

def test_shared_path_prefix_is_removed_from_sibling_options():
    from api.modules.rag_engine import _shorten_siblings

    nodes = [
        {"gtip_code": "841370219000",
         "description": "Sıvılar için pompalar > Diğer santrifüj pompalar > Dalgıç pompaları > Tek kademeli olanlar > Diğerleri"},
        {"gtip_code": "841370299000",
         "description": "Sıvılar için pompalar > Diğer santrifüj pompalar > Dalgıç pompaları > Çok kademeli olanlar > Diğerleri"},
    ]
    short = _shorten_siblings(nodes)
    texts = [n["branch_context"] for n in short]

    assert texts == ["Tek kademeli olanlar > Diğerleri", "Çok kademeli olanlar > Diğerleri"]
    # Kodlar korunur: kapalı küme sözleşmesi bozulmamalı.
    assert [n["gtip_code"] for n in short] == [n["gtip_code"] for n in nodes]


def test_prefix_stripping_stops_where_options_diverge():
    """Ayrım başlar başlamaz durulmalı; fazladan seviye atmak bilgi kaybıdır."""
    from api.modules.rag_engine import _shorten_siblings

    nodes = [
        {"gtip_code": "1", "description": "A > B > C > X"},
        {"gtip_code": "2", "description": "A > B > D > Y"},
    ]
    texts = [n["branch_context"] for n in _shorten_siblings(nodes)]
    assert texts == ["C > X", "D > Y"]


def test_no_stripping_when_nothing_is_shared():
    from api.modules.rag_engine import _shorten_siblings

    nodes = [
        {"gtip_code": "1", "description": "Cam eşya > Emniyet camları"},
        {"gtip_code": "2", "description": "Alüminyum > İnşaat aksamı"},
    ]
    short = _shorten_siblings(nodes)
    assert all("branch_context" not in n for n in short)


def test_single_option_is_left_untouched():
    """Karşılaştıracak kardeş yoksa tam yol bağlam olarak değerlidir."""
    from api.modules.rag_engine import _shorten_siblings

    nodes = [{"gtip_code": "1", "description": "A > B > C"}]
    assert _shorten_siblings(nodes) == nodes


def test_last_level_is_never_stripped_even_if_identical():
    """
    Tüm seçenekler 'Diğerleri' ile bitse bile son seviye durur; aksi halde
    seçenek metni tamamen boşalırdı.
    """
    from api.modules.rag_engine import _shorten_siblings

    nodes = [
        {"gtip_code": "1", "description": "A > Diğerleri"},
        {"gtip_code": "2", "description": "A > Diğerleri"},
    ]
    texts = [n.get("branch_context", n["description"]) for n in _shorten_siblings(nodes)]
    assert all(t.strip() for t in texts)
