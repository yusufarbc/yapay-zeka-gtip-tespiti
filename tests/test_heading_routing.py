"""Pozisyon yönlendirme deneyinin çevrimdışı doğrulanabilir parçaları.

Deneyin kararı (fasıl seçimini atlamak güvenli mi?) bu metriklere dayanacak.
Metrik yanlış hesaplanırsa mimari karar yanlış veriyle alınır; bu yüzden sıra,
recall, füzyon ve kapı taraması veritabanı ve Vertex gerektirmeden test edilir.
"""

import os
from types import SimpleNamespace

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USE_GCP_EMULATOR", "true")

from scripts.evaluate_heading_routing import (  # noqa: E402
    BM25Index,
    aggregate_precedents_by_heading,
    build_heading_documents,
    evaluate,
    gate_features,
    rank_of,
    recall_at,
    rrf_fuse,
    sweep_gate,
    tokenize,
)


def test_tokenize_folds_turkish_and_stems_suffixes():
    # "pompaları" ve "pompalar" aynı köke inmeli; aksi halde ekler eşleşmeyi bozar.
    assert tokenize("Santrifüj POMPALARI") == tokenize("santrifuj pompalar")
    assert "diger" not in tokenize("Diğerleri")
    assert tokenize("ve ile de") == []


def test_heading_documents_dedupe_repeated_path_segments():
    catalog = [
        {"gtip_code": "8413", "description": "Sıvılar için pompalar"},
        {"gtip_code": "841370", "description": "- Diğer santrifüj pompalar:"},
        {"gtip_code": "841370210000", "description": "Diğer santrifüj pompalar > Dalgıç pompaları > Diğerleri"},
        {"gtip_code": "841370290000", "description": "Diğer santrifüj pompalar > Dalgıç pompaları > Tek kademeli"},
    ]
    doc = build_heading_documents(catalog)["8413"]
    assert doc.startswith("Sıvılar için pompalar")
    assert doc.count("Dalgıç pompaları") == 1
    assert "Diğerleri" not in doc


def test_bm25_prefers_specific_heading():
    index = BM25Index({
        "8413": "Sıvılar için pompalar ; santrifüj pompalar ; dalgıç pompaları",
        "8516": "Elektrikli su ısıtıcıları ; saç kurutma makinaları",
        "6403": "Ayakkabılar ; dış tabanı kauçuk, üst kısmı deri",
    })
    ranking = index.rank("dalgıç santrifüj pompa")
    assert ranking[0][0] == "8413"
    assert index.rank("   ") == []


def test_precedent_votes_group_by_heading():
    precedents = [
        SimpleNamespace(gtip_code="8516.10.80.00.00", similarity_score=0.62),
        SimpleNamespace(gtip_code="8516.79.70.00.00", similarity_score=0.55),
        SimpleNamespace(gtip_code="7323.93.00.00.00", similarity_score=0.70),
    ]
    ranking = aggregate_precedents_by_heading(precedents)
    # En iyi benzerlik baskın: tek emsalli 7323 (0.70), iki emsalli 8516'nın (0.62+0.05) önünde.
    assert [key for key, _ in ranking] == ["7323", "8516"]
    assert ranking[1][1] == 0.67


def test_rank_of_counts_distinct_chapters():
    ranking = [("8516", 1.0), ("8509", 0.9), ("7323", 0.8)]
    assert rank_of(ranking, "732393000000", 4) == 3
    # 85 iki kez görünse de fasıl sırası 1, 73 ikinci fasıldır.
    assert rank_of(ranking, "732393000000", 2) == 2
    assert rank_of(ranking, "640399000000", 4) is None


def test_recall_counts_missing_as_miss():
    assert recall_at([1, 3, None, 5], 3) == 50.0
    assert recall_at([], 3) == 0.0


def test_rrf_rewards_agreement_across_methods():
    fused = rrf_fuse([
        [("8516", 0.9), ("8509", 0.8)],
        [("8509", 12.0), ("7323", 3.0)],
    ])
    assert fused[0][0] == "8509"


def test_gate_sweep_reports_recall_of_passed_only():
    rows = [
        {"gate": {"top1": 0.95}, "heading_rank": 1},
        {"gate": {"top1": 0.80}, "heading_rank": 2},
        {"gate": {"top1": 0.40}, "heading_rank": None},
    ]
    table = sweep_gate(rows, "top1", [0.5, 0.9])
    assert table[0]["passed"] == 2 and table[0]["recall@3_of_passed"] == 100.0
    assert table[1]["pass_rate"] == 33.33
    assert gate_features([])["margin"] == 0.0


def test_evaluate_groups_against_traversal_outcome():
    dataset = [
        {"reference_no": "R1", "expected_gtip": "851610800000", "description": "su ısıtıcı"},
        {"reference_no": "R2", "expected_gtip": "640399000000", "description": "deri ayakkabı"},
    ]
    fixed = {
        "R1": [("8516", 0.9)],
        "R2": [("4202", 0.9), ("6403", 0.8)],
    }
    traversal = {
        "R1": {"expected_gtip": "851610800000", "predicted_gtip": "851610800000", "status": "COMPLETED"},
        "R2": {"expected_gtip": "640399000000", "predicted_gtip": "420221000000", "status": "COMPLETED"},
    }
    report = evaluate(dataset, {"lexical": lambda s: fixed[s["reference_no"]]}, traversal, {"8516": 4, "4202": 3, "6403": 5})

    lexical = next(item for item in report["summary"] if item["method"] == "lexical")
    assert lexical["heading_recall@1"] == 50.0
    assert lexical["heading_recall@3"] == 100.0
    # Dolaşımın fasılda yanıldığı numunede yönlendirme doğru pozisyonu ilk 3'te buluyor.
    assert report["vs_traversal"]["traversal_wrong_chapter"] == {"n": 1, "fused_recall@3": 100.0, "fused_recall@5": 100.0}
    assert report["fused_top3_subheading_options"]["max"] == 8
