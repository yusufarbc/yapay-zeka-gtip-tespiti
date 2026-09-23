"""
Güven skorunu etiketli veri üzerinde kalibre eder.

SORUN
-----
Skor doğruyu yanlıştan ayırt etmiyordu:

  yanlış sınıflandırmaların 27/30'u -> 0.60
  tüm kararların        57/59'u     -> 0.60

Formül elle yazılmıştı ve ağırlıkları tahmine dayanıyordu. Skorun işe yaraması
için her sinyalin doğrulukla GERÇEKTEN ilişkili olduğunun ölçülmesi gerekir.

YÖNTEM
------
Benchmark her numune için ham sinyalleri ve doğruluk etiketini kaydediyor.
Bu araç:

  1. Her sinyal için, sinyalin bulunduğu ve bulunmadığı gruplardaki doğruluk
     oranını karşılaştırır (ayrım gücü).
  2. Mevcut skorun ayrım gücünü ölçer: doğru kararların ortalama skoru ile
     yanlışlarınkini karşılaştırır ve AUC hesaplar.
  3. Eşik taraması yapar: her eşik için kaç doğru karar boşuna işaretlenir
     (yanlış alarm) ve kaç yanlış karar yakalanır.

Kalibrasyon sonucu bir öneridir; ağırlıkları bu araç değil insan belirler.

Kullanım:
  python -m scripts.calibrate_confidence benchmark_results/<rapor>.json
"""

import argparse
import json
import os
import statistics
import sys
from typing import Any, Dict, List

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Ayrımı ölçülecek sinyaller. Sürekli olanlar eşikle ikiliye çevrilir.
BOOLEAN_SIGNALS = [
    "used_residual_fallback",
    "used_chapter_backtrack",
]
NUMERIC_SIGNALS = [
    ("btb_best_similarity", 0.5),
    ("ebti_best_similarity", 0.5),
    ("gir_key_count", 1),
    ("cited_chapter_note_count", 1),
    ("hitl_answer_count", 1),
    ("leaf_option_count", 4),
    ("heading_option_count", 20),
]


def _load(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        report = json.load(handle)
    samples = report.get("samples") or []
    if not samples:
        raise SystemExit(
            "Raporda 'samples' yok. Sinyal kaydı eklenmeden önce üretilmiş olabilir; "
            "benchmark'ı yeniden çalıştırın."
        )
    # Yalnız karar üretilen numuneler: cevapsız kalanda skor da yoktur.
    return [s for s in samples if s.get("status") == "COMPLETED"]


def _rate(rows: List[Dict[str, Any]], key: str = "correct_leaf") -> float:
    return sum(1 for r in rows if r.get(key)) / len(rows) if rows else 0.0


def auc(scores_pos: List[float], scores_neg: List[float]) -> float:
    """Doğru kararın yanlıştan yüksek skor alma olasılığı (0.5 = rastgele)."""
    if not scores_pos or not scores_neg:
        return 0.5
    wins = sum(
        1.0 if p > n else 0.5 if p == n else 0.0
        for p in scores_pos for n in scores_neg
    )
    return wins / (len(scores_pos) * len(scores_neg))


def main() -> int:
    parser = argparse.ArgumentParser(description="Güven skoru kalibrasyonu")
    parser.add_argument("report", help="benchmark_results/<rapor>.json")
    parser.add_argument("--target", default="correct_leaf",
                        choices=["correct_leaf", "correct_heading"])
    args = parser.parse_args()

    rows = _load(args.report)
    overall = _rate(rows, args.target)
    print(f"karar üretilen numune : {len(rows)}")
    print(f"genel doğruluk ({args.target}): %{overall * 100:.1f}")
    print()

    print("=== SİNYAL AYRIM GÜCÜ ===")
    print(f"{'sinyal':<30}{'var ise':>10}{'yok ise':>10}{'fark':>10}{'n(var)':>8}")
    print("-" * 68)

    findings = []
    checks = [(s, None) for s in BOOLEAN_SIGNALS] + [(s, t) for s, t in NUMERIC_SIGNALS]
    for signal, threshold in checks:
        if threshold is None:
            present = [r for r in rows if r.get(signal)]
            absent = [r for r in rows if not r.get(signal)]
            label = signal
        else:
            present = [r for r in rows if (r.get(signal) or 0) >= threshold]
            absent = [r for r in rows if (r.get(signal) or 0) < threshold]
            label = f"{signal} >= {threshold}"
        if not present or not absent:
            print(f"{label:<30}{'—':>10}{'—':>10}{'—':>10}{len(present):>8}   (tek gruplu)")
            continue
        a, b = _rate(present, args.target), _rate(absent, args.target)
        delta = a - b
        findings.append((abs(delta), label, delta, len(present)))
        print(f"{label:<30}{a * 100:>9.1f}%{b * 100:>9.1f}%{delta * 100:>+9.1f}%{len(present):>8}")

    print()
    print("En ayırt edici sinyaller:")
    for _, label, delta, n in sorted(findings, reverse=True)[:5]:
        yon = "doğruluğu ARTIRIYOR" if delta > 0 else "doğruluğu DÜŞÜRÜYOR"
        print(f"  {label:<32}{delta * 100:+6.1f}%  {yon}  (n={n})")

    print()
    print("=== MEVCUT SKORUN AYRIM GÜCÜ ===")
    pos = [r["confidence"] for r in rows if r.get(args.target)]
    neg = [r["confidence"] for r in rows if not r.get(args.target)]
    if pos and neg:
        print(f"doğru kararların ortalama skoru : {statistics.fmean(pos):.3f}")
        print(f"yanlış kararların ortalama skoru: {statistics.fmean(neg):.3f}")
        value = auc(pos, neg)
        print(f"AUC                             : {value:.3f}  "
              f"({'ayırt etmiyor' if value < 0.6 else 'zayıf' if value < 0.7 else 'kullanılabilir'})")
    else:
        print("tek sınıf: karşılaştırma yapılamaz")

    print()
    print("=== EŞİK TARAMASI ===")
    print(f"{'eşik':>8}{'işaretlenen':>13}{'yakalanan yanlış':>18}{'boşuna işaret':>16}")
    print("-" * 55)
    total_wrong = len(neg)
    for threshold in [round(x * 0.05, 2) for x in range(8, 20)]:
        flagged = [r for r in rows if r["confidence"] < threshold]
        caught = sum(1 for r in flagged if not r.get(args.target))
        false_alarm = len(flagged) - caught
        print(f"{threshold:>8.2f}{len(flagged):>13}"
              f"{f'{caught}/{total_wrong}':>18}{false_alarm:>16}")

    print()
    print("Yorum: 'boşuna işaret', doğru olduğu halde müşavire gönderilen karar")
    print("sayısıdır. Eşik yükseldikçe daha çok yanlış yakalanır ama doğru")
    print("kararlar da gereksiz yere işaretlenir. Denge ürün kararıdır.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
