"""
GTİP Tespit Karar Destek Sistemi - Otomatik Başarım & Accuracy Benchmark Testi.
Sistemin 2-hane (Fasıl), 4-hane (Pozisyon), 6-hane (HS) ve 12-hane (GTİP) düzeylerindeki doğruluğunu % olarak ölçer.
"""
import os
import sys
import time
import json
import argparse
from typing import List, Dict, Any

# Root dizini yola ekle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.graph.workflow import workflow_engine

def load_benchmark_dataset(test_set_path: str = None) -> List[Dict[str, Any]]:
    if test_set_path and os.path.exists(test_set_path):
        with open(test_set_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Varsayılan Kör Test Seti (tests/blind_benchmark.json)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    blind_path = os.path.join(base_dir, "tests", "blind_benchmark.json")
    if os.path.exists(blind_path):
        with open(blind_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Yoksa varsayılan dahili liste
    return [
        {
            "product_name": "iPhone 15 Pro 5G Akıllı Telefon",
            "raw_text": "Dokunmatik ekranlı 5G kablosuz hücresel haberleşme modüllü akıllı telefon",
            "expected_gtip": "8517.13.00.00.00",
            "category": "Elektronik / Telekomünikasyon"
        },
        {
            "product_name": "Şarjlı Döner Başlıklı Diş Fırçası",
            "raw_text": "Şarj edilebilir dahili 3.7V elektrik motorlu kişisel bakım diş fırçası",
            "expected_gtip": "8509.80.00.00.00",
            "category": "Elektrikli Ev Aleti / Kişisel Bakım"
        },
        {
            "product_name": "Hakiki Deri Erkek Ayakkabı",
            "raw_text": "Dış yüzeyi hakiki dana derisinden tabanı kauçuk erkek günlük ayakkabı",
            "expected_gtip": "6403.99.93.00.00",
            "category": "Ayakkabı / Saraciye"
        }
    ]

def run_accuracy_evaluation(test_set_path: str = None):
    dataset = load_benchmark_dataset(test_set_path)
    total_tests = len(dataset)

    print("=" * 80)
    print("GTIP TESPIT SISTEMI - OTOMATIK BASARIM & DOGRULUK EVALUATION RAPORU")
    print("=" * 80)
    print(f"Test Veri Seti Dosyası : {test_set_path or 'tests/blind_benchmark.json'}")
    print(f"Toplam Test Senaryosu  : {total_tests}\n")

    match_2digit = 0  # Fasıl doğruluğu
    match_4digit = 0  # Pozisyon doğruluğu
    match_6digit = 0  # HS Kodu doğruluğu
    match_12digit = 0 # Tam GTİP doğruluğu
    total_time_ms = 0

    print(f"{'No':<3} | {'Ürün / Kategori':<32} | {'Beklenen GTİP':<16} | {'Tahmin Edilen':<16} | {'Sonuç':<6}")
    print("-" * 80)

    for idx, item in enumerate(dataset, 1):
        start = time.time()
        decision = workflow_engine.start_analysis(item["raw_text"])
        duration = (time.time() - start) * 1000
        total_time_ms += duration

        pred_gtip = decision.gtip_code or "BELİRSİZ"
        exp_gtip = item["expected_gtip"]

        exp_clean = exp_gtip.replace(".", "")
        pred_clean = pred_gtip.replace(".", "")

        is_2d = pred_clean[:2] == exp_clean[:2]
        is_4d = pred_clean[:4] == exp_clean[:4]
        is_6d = pred_clean[:6] == exp_clean[:6]
        is_12d = pred_clean[:12] == exp_clean[:12]

        if is_2d: match_2digit += 1
        if is_4d: match_4digit += 1
        if is_6d: match_6digit += 1
        if is_12d: match_12digit += 1

        status_icon = "TAM" if is_12d else ("6D" if is_6d else ("4D" if is_4d else ("2D" if is_2d else "FAIL")))
        prod_title = f"{item['product_name'][:30]}"
        print(f"{idx:<3} | {prod_title:<32} | {exp_gtip:<16} | {pred_gtip:<16} | {status_icon:<6}")

    avg_time = total_time_ms / total_tests if total_tests > 0 else 0

    acc_2d = (match_2digit / total_tests) * 100 if total_tests > 0 else 0
    acc_4d = (match_4digit / total_tests) * 100 if total_tests > 0 else 0
    acc_6d = (match_6digit / total_tests) * 100 if total_tests > 0 else 0
    acc_12d = (match_12digit / total_tests) * 100 if total_tests > 0 else 0

    print("=" * 80)
    print("ISTATISTIKSEL BASARIM OZETI (ACCURACY METRICS):")
    print("=" * 80)
    print(f"* 2 Haneli Fasıl Doğruluğu (Chapter Accuracy) : %{acc_2d:.1f}")
    print(f"* 4 Haneli Pozisyon Doğruluğu (Heading Acc.)  : %{acc_4d:.1f}")
    print(f"* 6 Haneli HS Kodu Doğruluğu (HS Code Acc.)   : %{acc_6d:.1f}")
    print(f"* 12 Haneli Tam GTİP Doğruluğu (12-Digit Acc.): %{acc_12d:.1f}")
    print(f"* Ortalama Analiz Yanıt Süresi               : {avg_time:.2f} ms")
    print("=" * 80)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-set", help="Kör benchmark test dosyası (JSON)", default=None)
    args = parser.parse_args()
    run_accuracy_evaluation(args.test_set)
