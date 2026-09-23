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


def test_expert_answers_the_option_matching_the_expected_code():
    """
    Gözetimsiz benchmark'ta bekleyen soru da ölü uç da 'kod üretmedi' görünür.
    Uzman izi ikisini ayırır: soru cevaplanabilir, ölü uç cevaplanamaz.
    """
    from types import SimpleNamespace

    from scripts.evaluate_gtip_benchmark import answer_as_expert

    waiting = SimpleNamespace(
        status="WAITING_FOR_USER",
        session_id="s1",
        gtip_code=None,
        hitl_question=SimpleNamespace(
            question_id="q1",
            options=[
                SimpleNamespace(option_id="DISC_0", impact_data={"selected_branch": "7005"}),
                SimpleNamespace(option_id="DISC_1", impact_data={"selected_branch": "7007"}),
                SimpleNamespace(option_id="DISC_2", impact_data={"selected_branch": ""}),
            ],
        ),
    )
    resumed = SimpleNamespace(status="COMPLETED", gtip_code="7007.19.80.00.00",
                              session_id="s1", hitl_question=None)
    picked = {}

    class Engine:
        def resume_analysis(self, session_id, selected_option_id, question_id):
            picked["option"] = selected_option_id
            return resumed

    result = answer_as_expert(waiting, "700719800000", Engine())
    assert picked["option"] == "DISC_1"
    assert result.status == "COMPLETED"


def test_expert_gives_up_when_no_official_branch_holds_the_answer():
    """Doğru cevabı içermeyen bir soru yanlış sorulmuştur; bu bir başarısızlıktır."""
    from types import SimpleNamespace

    from scripts.evaluate_gtip_benchmark import answer_as_expert

    waiting = SimpleNamespace(
        status="WAITING_FOR_USER",
        session_id="s1",
        gtip_code=None,
        hitl_question=SimpleNamespace(
            question_id="q1",
            options=[
                SimpleNamespace(option_id="DISC_0", impact_data={"selected_branch": "8471"}),
                SimpleNamespace(option_id="DISC_1", impact_data={"selected_branch": "8517"}),
            ],
        ),
    )

    class Engine:
        def resume_analysis(self, **kwargs):
            raise AssertionError("uzman cevaplamamalıydı")

    result = answer_as_expert(waiting, "700719800000", Engine())
    assert result.status == "WAITING_FOR_USER"


def test_auc_measures_ranking_not_absolute_scores():
    """
    AUC, doğru kararın yanlıştan yüksek skor alma olasılığıdır. Skorun ayırt
    edip etmediğini ölçmenin doğru yolu budur: ortalamalara bakmak, herkesin
    aynı skoru aldığı bir sistemde yanıltır.
    """
    from scripts.calibrate_confidence import auc

    assert auc([0.9, 0.8], [0.2, 0.1]) == 1.0        # kusursuz ayrım
    assert auc([0.1, 0.2], [0.8, 0.9]) == 0.0        # tersine ayrım
    assert auc([0.6, 0.6], [0.6, 0.6]) == 0.5        # hiç ayırt etmiyor
    assert auc([], [0.5]) == 0.5                      # veri yok
