"""
GTİP Karar Destek Sistemi — Ground-Truth Benchmark ve Doğruluk Değerlendirme Aracı.

Ölçüm kümesi elle yazılmış örneklerden değil, Cloud SQL'deki GERÇEK Ticaret
Bakanlığı BTB kararlarından üretilir: her kayıt bir (ürün açıklaması, resmî GTİP)
çiftidir, yani bedava etiketli veridir.

Sızıntı kontrolü (kritik): Bir numunenin kendi BTB kaydı emsal olarak geri
gelirse `exact_btb_candidate` birebir eşleşme verip kodu doğrudan kopyalar ve
ölçüm anlamsızlaşır. Bu yüzden her çağrıda numunenin referans numarası
`exclude_btb_refs` ile emsal havuzundan çıkarılır.

Kullanım:
  python -m scripts.evaluate_gtip_benchmark --sample 300
  python -m scripts.evaluate_gtip_benchmark --sample 300 --baseline benchmark_results/<dosya>.json
"""

import argparse
import collections
import datetime
import json
import logging
import os
import random
import re
import statistics
import sys
import time
from typing import Any, Dict, List, Optional

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GTIPBenchmark")

DEFAULT_SEED = 42

# Container'da /app root olmayan `app` kullanicisi icin yazilabilir degildir
# (Dockerfile ayrica --chown ile yalniz okuma verir). Yerelde repo altina,
# container'da gecici dizine yazilir; kalicilik GCS yuklemesiyle saglanir.
def _default_results_dir() -> str:
    candidate = os.path.join(root_dir, "benchmark_results")
    try:
        os.makedirs(candidate, exist_ok=True)
        probe = os.path.join(candidate, ".write_probe")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("")
        os.remove(probe)
        return candidate
    except OSError:
        import tempfile
        fallback = os.path.join(tempfile.gettempdir(), "benchmark_results")
        os.makedirs(fallback, exist_ok=True)
        return fallback


RESULTS_DIR = os.getenv("BENCHMARK_RESULTS_DIR") or _default_results_dir()


def upload_to_gcs(local_path: str) -> Optional[str]:
    """Raporu GCS'e yukler. Cloud Run Job'un dosya sistemi kalici degildir."""
    bucket_name = os.getenv("GCS_BUCKET_NAME", "").strip()
    if not bucket_name:
        return None
    try:
        from google.cloud import storage

        blob_name = f"benchmark_results/{os.path.basename(local_path)}"
        storage.Client().bucket(bucket_name).blob(blob_name).upload_from_filename(local_path)
        return f"gs://{bucket_name}/{blob_name}"
    except Exception as exc:
        logger.warning("Rapor GCS'e yuklenemedi (%s); yerel kopya: %s", exc, local_path)
        return None


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


# ──────────────────────────────────────────────────────────────────────────────
# Holdout kümesi
# ──────────────────────────────────────────────────────────────────────────────

def stratify_by_chapter(
    candidates: List[Dict[str, Any]],
    sample_size: int,
    seed: int = DEFAULT_SEED,
) -> List[Dict[str, Any]]:
    """
    Fasıl başına tavan uygulayarak dengeli, tekrarlanabilir bir alt küme seçer.

    Korpus 84/85 fasıllarında yoğun (~%52); düz rastgele örnekleme 61 faslın
    çoğunu hiç temsil etmez ve doğruluk iki faslın performansına indirgenir.

    Saf fonksiyondur (veritabanı gerektirmez), bu yüzden çevrimdışı test edilir.
    """
    if sample_size <= 0 or not candidates:
        return []

    rng = random.Random(seed)
    # Veritabanı satırları ORDER BY olmadan fiziksel sırayla gelir ve bu sıra
    # tablo güncellendikçe değişir; aynı tohum farklı numuneler seçiyordu
    # (iki koşu 120 numunenin yalnız 60'ında örtüştü). Karıştırmadan önce
    # sabit bir sıraya dizilir.
    pool = sorted(candidates, key=lambda item: item["reference_no"])
    rng.shuffle(pool)

    by_chapter: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for item in pool:
        by_chapter[item["expected_chapter"]].append(item)

    per_chapter = max(1, sample_size // max(1, len(by_chapter)))
    holdout: List[Dict[str, Any]] = []
    for chapter in sorted(by_chapter):
        holdout.extend(by_chapter[chapter][:per_chapter])

    # Tavan nedeniyle hedefin altında kalındıysa kalan havuzdan tamamla.
    if len(holdout) < sample_size:
        chosen = {item["reference_no"] for item in holdout}
        for item in pool:
            if len(holdout) >= sample_size:
                break
            if item["reference_no"] not in chosen:
                holdout.append(item)
                chosen.add(item["reference_no"])

    rng.shuffle(holdout)
    return holdout[:sample_size]


def build_holdout(sample_size: int = 300, seed: int = DEFAULT_SEED) -> List[Dict[str, Any]]:
    """
    Gerçek BTB kararlarından fasıl-stratifiye, tekrarlanabilir bir holdout üretir.

    `load_btb_catalog()` KULLANILMAZ: o katalog gerçek BTB'lerle TGTC cetvelinden
    türetilmiş `TGTC2026-` önekli sahte kayıtları karıştırır. Ground truth için
    yalnız `gumruk_emsal_kararlar` tablosundaki `karar_tipi='BTB'` satırları geçerlidir.
    """
    from api.db.database import SessionLocal, GumrukEmsalKararModel

    with SessionLocal() as session:
        rows = session.query(
            GumrukEmsalKararModel.referans_no,
            GumrukEmsalKararModel.gtip_kodu,
            GumrukEmsalKararModel.esya_tanimi,
            GumrukEmsalKararModel.chapter_code,
        ).filter(GumrukEmsalKararModel.karar_tipi == "BTB").all()

    candidates: List[Dict[str, Any]] = []
    for ref_no, gtip, desc, chapter in rows:
        code = _digits(gtip)
        description = str(desc or "").strip()
        # Yalnız 12 haneli ve anlamlı açıklaması olan kararlar ölçülebilir.
        if len(code) != 12 or len(description) < 40:
            continue
        if not ref_no:
            continue
        candidates.append({
            "reference_no": str(ref_no),
            "expected_gtip": code,
            "expected_chapter": code[:2],
            "expected_heading": code[:4],
            "expected_subheading": code[:6],
            "description": description,
        })

    if not candidates:
        raise RuntimeError(
            "Ground-truth BTB kaydı bulunamadı. Cloud SQL bağlantısını doğrulayın "
            "(yerelde SQLite fallback'e düşülmüş olabilir)."
        )

    holdout = stratify_by_chapter(candidates, sample_size, seed)
    logger.info(
        "Holdout hazır: %d numune / %d fasıl (korpus: %d uygun BTB kaydı)",
        len(holdout),
        len({item["expected_chapter"] for item in holdout}),
        len(candidates),
    )
    return holdout


# ──────────────────────────────────────────────────────────────────────────────
# Değerlendirme
# ──────────────────────────────────────────────────────────────────────────────

MAX_EXPERT_ANSWERS = 4


def answer_as_expert(decision: Any, expected_gtip: str, workflow_engine: Any) -> Any:
    """Bekleyen teknik ayrım sorularını doğru cevabı bilen bir müşavir gibi yanıtlar.

    Benchmark gözetimsiz çalıştığı için soru soran her karar cevapsız kalıyordu.
    Bu, çıkmazı sorulabilir bir soruya çevirmenin değerini ölçülemez kılıyordu:
    hem ölü uç hem de bekleyen soru "kod üretmedi" olarak görünüyordu.

    Burada uzman, her dallanmada beklenen GTİP ile ön-eki uyuşan resmî seçeneği
    işaretler. Bu, gerçek kullanımdaki ortalama müşaviri değil, ULAŞILABİLİR
    doğruluğun üst sınırını ölçer: sistem doğru soruyu soruyor mu?
    """
    for _ in range(MAX_EXPERT_ANSWERS):
        if decision.status != "WAITING_FOR_USER" or not decision.hitl_question:
            return decision

        chosen = None
        # Ürün bilgisi teyidi (PROFILE): BTB kaydı malzemeyi ayrıca etiketlemez,
        # bu yüzden uzman modelin varsayımını kabul eder. Bu, profil sorusunun
        # kendisini değil, sorudan sonraki sınıflandırmayı ölçer.
        if getattr(decision, "state_machine_stage", None) == "PROFILE_QUESTION":
            chosen = next(
                (o for o in decision.hitl_question.options if (o.impact_data or {}).get("inferred") == "true"),
                None,
            )
        for option in ([] if chosen else decision.hitl_question.options):
            branch = _digits((option.impact_data or {}).get("selected_branch"))
            if branch and expected_gtip.startswith(branch):
                chosen = option
                break
        if chosen is None:
            # Hiçbir resmî dal doğru cevabı içermiyor: müşavir de seçemezdi.
            # Bu, sorunun yanlış sorulduğu anlamına gelir ve başarısızlıktır.
            return decision

        try:
            decision = workflow_engine.resume_analysis(
                session_id=decision.session_id,
                selected_option_id=chosen.option_id,
                question_id=decision.hitl_question.question_id,
            )
        except Exception as exc:
            logger.debug("Uzman cevabı uygulanamadı: %s", exc)
            return decision
    return decision

ABLATION_FLAGS = (
    "SELECTION_USE_RAW_TEXT",
    "SELECTION_USE_PRECEDENTS",
    "SELECTION_USE_CHAPTER_NOTES",
)
# Kanıt değil dolaşım biçimi: baseline'a dahil değildir, ayrıca kapatılır.
ROUTING_FLAGS = ("HEADING_ROUTING_ENABLED", "CHAPTER_EXCLUSION_CHECK_ENABLED", "CHAPTER_FIT_CHECK_ENABLED")
# Ürün profili ve teyit sorusu; kanıt değil giriş biçimidir, ayrıca kapatılır.
PROFILE_FLAGS = ("PRODUCT_PROFILE_ENABLED", "PROFILE_CONFIRMATION_ENABLED")


def run_benchmark(
    sample_size: int = 300,
    seed: int = DEFAULT_SEED,
    dataset: Optional[List[Dict[str, Any]]] = None,
    ablate: Optional[List[str]] = None,
) -> Dict[str, Any]:
    from api.config import settings
    from api.graph.workflow import workflow_engine

    # Ablasyon: kanıt enjeksiyonunu kapatarak her maddenin katkısını tek tek ölç.
    # Hepsi kapalıyken alınan ölçüm baseline'dır.
    for flag in (ablate or []):
        if flag not in ABLATION_FLAGS + ROUTING_FLAGS + PROFILE_FLAGS:
            raise SystemExit(
                f"Bilinmeyen ablasyon bayrağı: {flag} (geçerli: {ABLATION_FLAGS + ROUTING_FLAGS + PROFILE_FLAGS})"
            )
        setattr(settings, flag, False)
    active_flags = {flag: bool(getattr(settings, flag)) for flag in ABLATION_FLAGS + ROUTING_FLAGS + PROFILE_FLAGS}
    logger.info("Kanıt bayrakları: %s", active_flags)

    test_set = dataset or build_holdout(sample_size, seed)
    total = len(test_set)

    hits = {"chapter": 0, "heading": 0, "subheading": 0, "leaf": 0}
    expert_hits = {"leaf": 0, "heading": 0}
    expert_completed = 0
    statuses: collections.Counter = collections.Counter()
    residual_fallbacks = 0
    profile_questions = 0
    latencies: List[float] = []
    failures: List[Dict[str, Any]] = []
    samples: List[Dict[str, Any]] = []

    logger.info("=== Benchmark başlıyor: %d numune, model=%s ===",
                total, settings.REASONING_LLM_MODEL)

    for index, sample in enumerate(test_set, 1):
        started = time.perf_counter()
        try:
            decision = workflow_engine.start_analysis(
                sample["description"],
                # Sızıntı kontrolü: numunenin kendi kararı emsal havuzundan çıkarılır.
                exclude_btb_refs={sample["reference_no"]},
            )
        except Exception as exc:
            logger.exception("Numune çalıştırılamadı (%s)", sample["reference_no"])
            statuses["EXCEPTION"] += 1
            failures.append({
                "reference_no": sample["reference_no"],
                "expected_gtip": sample["expected_gtip"],
                "error": str(exc),
            })
            continue
        latencies.append((time.perf_counter() - started) * 1000)

        statuses[decision.status] += 1
        if getattr(decision, "state_machine_stage", None) == "PROFILE_QUESTION":
            profile_questions += 1
        predicted = _digits(decision.gtip_code)

        matched = {
            "chapter": predicted[:2] == sample["expected_chapter"] if predicted else False,
            "heading": predicted[:4] == sample["expected_heading"] if predicted else False,
            "subheading": predicted[:6] == sample["expected_subheading"] if predicted else False,
            "leaf": predicted == sample["expected_gtip"] if predicted else False,
        }
        for key, ok in matched.items():
            if ok:
                hits[key] += 1

        # `workflow._complete` kalıntı dalı kullanıldığında bu deterministik
        # işareti basar (rag_engine traversal["used_residual_fallback"]).
        if any(note.startswith("RESIDUAL_FALLBACK:") for note in decision.audit_notes):
            residual_fallbacks += 1

        # Uzman izi: bekleyen soruları doğru cevabı bilen bir müşavir yanıtlasa
        # sistem nereye varırdı? Otomatik metrikler bozulmadan ayrı sayılır.
        expert_decision = decision
        if decision.status == "WAITING_FOR_USER":
            expert_decision = answer_as_expert(decision, sample["expected_gtip"], workflow_engine)
        expert_predicted = _digits(expert_decision.gtip_code)
        if expert_decision.status == "COMPLETED":
            expert_completed += 1
        if expert_predicted:
            if expert_predicted[:4] == sample["expected_heading"]:
                expert_hits["heading"] += 1
            if expert_predicted == sample["expected_gtip"]:
                expert_hits["leaf"] += 1

        # Kalibrasyon verisi: her numune için ham sinyaller + doğruluk etiketi.
        # Skorun doğrulukla korelasyonu ancak bu eşleşmeden ölçülebilir.
        samples.append({
            "reference_no": sample["reference_no"],
            "expected_gtip": sample["expected_gtip"],
            "predicted_gtip": predicted or None,
            "status": decision.status,
            "confidence": decision.confidence_score,
            "correct_heading": matched["heading"],
            "correct_leaf": matched["leaf"],
            **(decision.decision_signals or {}),
        })

        if not matched["heading"]:
            failures.append({
                "reference_no": sample["reference_no"],
                "description": sample["description"][:200],
                "expected_gtip": sample["expected_gtip"],
                "predicted_gtip": predicted or None,
                "status": decision.status,
                "confidence": decision.confidence_score,
            })

        icon = "OK " if matched["heading"] else ("~  " if matched["chapter"] else "X  ")
        logger.info(
            "[%d/%d] %s beklenen=%s tahmin=%s durum=%s",
            index, total, icon,
            sample["expected_heading"], predicted[:4] or "----", decision.status,
        )

    def pct(value: int) -> float:
        return round(value / total * 100.0, 2) if total else 0.0

    completed = statuses.get("COMPLETED", 0)
    report: Dict[str, Any] = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": settings.REASONING_LLM_MODEL,
        "extractor_model": settings.EXTRACTOR_LLM_MODEL,
        "sample_size": total,
        "seed": seed,
        # Karşılaştırmanın anlamlı olması için hangi kanıtın açık olduğu kaydedilir.
        "evidence_flags": active_flags,
        "metrics": {
            # Doğruluk: TÜM numuneler üzerinden (cevapsız kalmak da başarısızlıktır).
            "chapter_acc": pct(hits["chapter"]),
            "heading_acc": pct(hits["heading"]),
            "subheading_acc": pct(hits["subheading"]),
            "leaf_acc": pct(hits["leaf"]),
            # Kapsam: doğruluktan ayrı izlenir; model soru sorarsa doğruluk düşer
            # ama bu bir hata değil, kapsam kaybıdır.
            "coverage": pct(completed),
            "hitl_rate": pct(statuses.get("WAITING_FOR_USER", 0)),
            "manual_review_rate": pct(statuses.get("MANUAL_REVIEW_REQUIRED", 0)),
            "exception_rate": pct(statuses.get("EXCEPTION", 0)),
            "residual_fallback_rate": pct(residual_fallbacks),
            # Sınıflandırmadan önce ürün bilgisi (malzeme / eşya türü) sorulan oran.
            "profile_question_rate": pct(profile_questions),
            # Uzman müşavir teknik ayrımları yanıtlasa ulaşılabilir sonuç.
            # Çıkmazı soruya çevirmenin değeri yalnız burada görünür: ölü uç
            # cevaplanamaz, bekleyen soru cevaplanabilir.
            "coverage_with_expert": pct(expert_completed),
            "heading_acc_with_expert": pct(expert_hits["heading"]),
            "leaf_acc_with_expert": pct(expert_hits["leaf"]),
            # Tamamlananlar içindeki doğruluk (kapsamdan arındırılmış)
            "leaf_acc_of_completed": (
                round(hits["leaf"] / completed * 100.0, 2) if completed else 0.0
            ),
        },
        "latency_ms": {
            "p50": round(statistics.median(latencies), 1) if latencies else 0.0,
            "p95": round(
                statistics.quantiles(latencies, n=20)[18], 1
            ) if len(latencies) >= 20 else (round(max(latencies), 1) if latencies else 0.0),
            "mean": round(statistics.fmean(latencies), 1) if latencies else 0.0,
        },
        "status_breakdown": dict(statuses),
        "failures": failures[:50],
        # Her numunenin sinyalleri ve doğruluk etiketi: güven skorunun
        # kalibrasyonu bu veri üzerinde yapılır.
        "samples": samples,
    }

    logger.info("=== SONUÇLAR ===")
    for key, value in report["metrics"].items():
        logger.info("%-26s %%%s", key, value)
    logger.info("%-26s p50=%sms p95=%sms", "latency", report["latency_ms"]["p50"], report["latency_ms"]["p95"])
    return report


def load_report(path: str) -> Dict[str, Any]:
    """Raporu yerel dosyadan veya gs:// yolundan okur.

    Cloud Run Job raporları GCS'e yüklendiği için karşılaştırmanın önce indirme
    adımı gerektirmesi runbook'u gereksiz uzatıyordu.
    """
    if path.startswith("gs://"):
        from google.cloud import storage

        bucket_name, _, blob_name = path[5:].partition("/")
        payload = storage.Client().bucket(bucket_name).blob(blob_name).download_as_bytes()
        return json.loads(payload.decode("utf-8"))
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def compare_to_baseline(report: Dict[str, Any], baseline_path: str) -> None:
    baseline = load_report(baseline_path)

    logger.info("=== BASELINE KARŞILAŞTIRMASI (%s) ===", os.path.basename(baseline_path))
    logger.info("baseline bayrakları: %s", baseline.get("evidence_flags"))
    logger.info("şimdiki bayraklar  : %s", report.get("evidence_flags"))
    logger.info("%-26s %8s %8s %8s", "metrik", "baseline", "şimdi", "fark")
    for key, current in report["metrics"].items():
        previous = baseline.get("metrics", {}).get(key)
        if previous is None:
            continue
        delta = round(current - previous, 2)
        marker = "  " if abs(delta) < 0.01 else ("+ " if delta > 0 else "- ")
        logger.info("%-26s %8s %8s %s%s", key, previous, current, marker, abs(delta))


def main() -> int:
    parser = argparse.ArgumentParser(description="GTİP sınıflandırma benchmark'ı")
    parser.add_argument("--sample", type=int, default=300, help="Numune sayısı")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Örnekleme tohumu")
    parser.add_argument(
        "--baseline", type=str, default=None,
        help="Karşılaştırılacak baseline raporu (yerel yol veya gs://bucket/yol.json)",
    )
    parser.add_argument("--out", type=str, default=None, help="Çıktı dosyası (varsayılan: benchmark_results/)")
    parser.add_argument(
        "--ablate", action="append", default=[], metavar="FLAG",
        help=("Kapatılacak kanıt bayrağı; birden çok kez verilebilir. "
              "Baseline için: --ablate SELECTION_USE_RAW_TEXT "
              "--ablate SELECTION_USE_PRECEDENTS --ablate SELECTION_USE_CHAPTER_NOTES"),
    )
    parser.add_argument(
        "--baseline-run", action="store_true",
        help="Tüm kanıt bayraklarını kapatır (--ablate üçünü birden vermeye eşdeğer).",
    )
    args = parser.parse_args()

    ablate = list(args.ablate)
    if args.baseline_run:
        ablate = list(ABLATION_FLAGS)

    report = run_benchmark(sample_size=args.sample, seed=args.seed, ablate=ablate)

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = "baseline" if set(ABLATION_FLAGS) <= set(ablate) else ("ablate" if ablate else "full")
    out_path = args.out or os.path.join(RESULTS_DIR, f"benchmark-{label}-{stamp}.json")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    logger.info("Rapor yazıldı: %s", out_path)

    gcs_uri = upload_to_gcs(out_path)
    if gcs_uri:
        logger.info("Rapor GCS'e yüklendi: %s", gcs_uri)

    # Ölçüm tamamlandıysa rapor yazımı başarısız olsa bile sonuçlar loglanmıştır;
    # yazma hatası bütün koşuyu boşa çıkarmamalı.

    if args.baseline:
        compare_to_baseline(report, args.baseline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
