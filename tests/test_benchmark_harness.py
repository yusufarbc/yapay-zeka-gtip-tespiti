"""Benchmark değerlendirme aracının çevrimdışı doğrulanabilir parçaları.

Holdout üretimi ve metrik hesabı Vertex/Cloud SQL gerektirmeden test edilir;
canlı ölçüm ayrıca `gtip-benchmark` Cloud Run Job'u ile çalıştırılır.
"""

import collections

from scripts.evaluate_gtip_benchmark import run_benchmark, stratify_by_chapter


def _candidate(ref: str, gtip: str, desc: str = "x" * 60) -> dict:
    return {
        "reference_no": ref,
        "expected_gtip": gtip,
        "expected_chapter": gtip[:2],
        "expected_heading": gtip[:4],
        "expected_subheading": gtip[:6],
        "description": desc,
    }


def _skewed_corpus() -> list:
    """Üretim korpusunu taklit eder: 84/85 baskın, kuyrukta seyrek fasıllar."""
    corpus = []
    for index in range(300):
        corpus.append(_candidate(f"BTB-84-{index}", f"8471300000{index % 10}0"))
    for index in range(300):
        corpus.append(_candidate(f"BTB-85-{index}", f"8518300000{index % 10}0"))
    for chapter in ("39", "61", "70", "73", "90", "94"):
        for index in range(5):
            corpus.append(_candidate(f"BTB-{chapter}-{index}", f"{chapter}0130000{index}00"))
    return corpus


def test_stratification_is_deterministic():
    corpus = _skewed_corpus()
    first = stratify_by_chapter(corpus, 40, seed=42)
    second = stratify_by_chapter(corpus, 40, seed=42)
    assert [item["reference_no"] for item in first] == [item["reference_no"] for item in second]


def test_stratification_rescues_rare_chapters_from_a_skewed_corpus():
    """Düz rastgele örneklemede seyrek fasıllar kaybolur; tavan bunu önlemeli."""
    corpus = _skewed_corpus()
    holdout = stratify_by_chapter(corpus, 40, seed=42)

    assert len(holdout) == 40
    chapters = collections.Counter(item["expected_chapter"] for item in holdout)
    # Korpusun %95'i 84/85 olmasına rağmen seyrek fasılların tamamı temsil edilmeli.
    assert {"39", "61", "70", "73", "90", "94"} <= set(chapters)
    # Ve baskın fasıllar örneklemi ele geçirmemeli.
    assert chapters["84"] + chapters["85"] < len(holdout) * 0.75


def test_stratification_never_repeats_a_sample():
    holdout = stratify_by_chapter(_skewed_corpus(), 120, seed=7)
    refs = [item["reference_no"] for item in holdout]
    assert len(refs) == len(set(refs))


def test_stratification_handles_degenerate_inputs():
    assert stratify_by_chapter([], 10) == []
    assert stratify_by_chapter(_skewed_corpus(), 0) == []


def test_report_separates_accuracy_from_coverage():
    """
    Cevapsız kalan numune doğruluğu düşürmeli ama kapsam ayrı raporlanmalı.

    Çevrimdışı ortamda katalog boş olduğu için her numune MANUAL_REVIEW döner;
    bu, metrik ayrışmasını doğrulamak için yeterlidir.
    """
    dataset = [_candidate("BTB-TEST-1", "847130000010")]
    report = run_benchmark(dataset=dataset)

    metrics = report["metrics"]
    assert set(metrics) >= {
        "chapter_acc", "heading_acc", "subheading_acc", "leaf_acc",
        "coverage", "hitl_rate", "manual_review_rate", "residual_fallback_rate",
    }
    # Karar üretilemediği için doğruluk 0, ama bu bir "yanlış sınıflandırma" değil:
    # kapsam metriği bunu ayrı gösterir.
    assert metrics["leaf_acc"] == 0.0
    assert metrics["coverage"] + metrics["hitl_rate"] + metrics["manual_review_rate"] \
        + metrics["exception_rate"] == 100.0
    assert report["sample_size"] == 1
    assert "latency_ms" in report
