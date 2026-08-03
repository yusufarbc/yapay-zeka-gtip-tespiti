"""
GTİP Tespit Karar Destek Sistemi - Otomatik Başarım & Accuracy Benchmark Testi.
Sistemin 2-hane (Fasıl), 4-hane (Pozisyon), 6-hane (HS) ve 12-hane (GTİP) düzeylerindeki doğruluğunu % olarak ölçer.
"""
import os
import sys
import time
from typing import List, Dict, Any

# Root dizini yola ekle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.graph.workflow import workflow_engine

# Gerçek Dünya Benchmark Test Veri Seti (Çeşitli Fasıllardan 12 Ürün)
BENCHMARK_TEST_DATASET = [
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
    },
    {
        "product_name": "Deri Kadın El Çantası",
        "raw_text": "Dış yüzeyi hakiki deriden üretilmiş omuz askılı kadın el çantası",
        "expected_gtip": "4202.21.00.00.00",
        "category": "Deri Eşya / El Çantaları"
    },
    {
        "product_name": "%100 Pamuk Erkek T-Shirt",
        "raw_text": "%100 pamuk örme kumaştan mamul erkek kısa kollu tişört penye",
        "expected_gtip": "6109.10.00.00.00",
        "category": "Tekstil / Örme Giyim"
    },
    {
        "product_name": "Kadın Parfümü Eau de Parfum",
        "raw_text": "Cam şişe içerisinde sprey valfli sıvı formda sunulan kadın parfümü 100ml",
        "expected_gtip": "3303.00.10.00.00",
        "category": "Kozmetik / Parfümeri"
    },
    {
        "product_name": "Ahşap Yemek Masası",
        "raw_text": "Ahşap malzemeden imal edilmiş ev tipi 6 kişilik yemek masası",
        "expected_gtip": "9403.60.10.00.00",
        "category": "Ev / Mobilya"
    },
    {
        "product_name": "Pille Çalışan Çocuk Yarış Arabası",
        "raw_text": "Plastik malzemeden imal edilmiş pille çalışan uzaktan kumandalı oyuncak araba",
        "expected_gtip": "9503.00.70.00.00",
        "category": "Oyuncaklar / Oyun Eşyaları"
    },
    {
        "product_name": "Demonte İki Tekerlekli Bisiklet",
        "raw_text": "Kutu içerisinde parçalar halinde sökülmüş demonte iki tekerlekli bisiklet",
        "expected_gtip": "8712.00.30.00.00",
        "category": "Taşıtlar / Ulaşım"
    },
    {
        "product_name": "15.6 inç Dizüstü Bilgisayar Notebook",
        "raw_text": "Ağırlığı 1.8 kg olan dahili klavyeli bataryalı dizüstü bilgisayar laptop",
        "expected_gtip": "8471.30.00.00.11",
        "category": "Bilgi İşlem / Bilgisayarlar"
    },
    {
        "product_name": "No-Frost Kompresörlü Buzdolabı",
        "raw_text": "Ev tipi çift kapılı donduruculu kombi buzdolabı soğutucu",
        "expected_gtip": "8418.10.20.00.00",
        "category": "Mekanik Ev Aletleri"
    },
    {
        "product_name": "%60 Pamuk / %40 Polyester Dokuma Kumaş",
        "raw_text": "%60 pamuk %40 polyester karışımı m² ağırlığı 140 gram dokuma kumaş",
        "expected_gtip": "5208.32.00.00.00",
        "category": "Tekstil Kumaşlar"
    }
]

def run_accuracy_evaluation():
    print("=" * 80)
    print("GTIP TESPIT SISTEMI - OTOMATIK BASARIM & DOGRULUK EVALUATION RAPORU")
    print("=" * 80)

    total_tests = len(BENCHMARK_TEST_DATASET)
    match_2digit = 0  # Fasıl doğruluğu
    match_4digit = 0  # Pozisyon doğruluğu
    match_6digit = 0  # HS Kodu doğruluğu
    match_12digit = 0 # Tam GTİP doğruluğu
    total_time_ms = 0

    print(f"\nToplam Test Senaryosu Sayısı: {total_tests}\n")
    print(f"{'No':<3} | {'Ürün / Kategori':<32} | {'Beklenen GTİP':<16} | {'Tahmin Edilen':<16} | {'Sonuç':<6}")
    print("-" * 80)

    for idx, item in enumerate(BENCHMARK_TEST_DATASET, 1):
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

        status_icon = "TAM" if is_12d else ("6D" if is_6d else ("4D" if is_4d else "FAIL"))
        prod_title = f"{item['product_name'][:30]}"
        print(f"{idx:<3} | {prod_title:<32} | {exp_gtip:<16} | {pred_gtip:<16} | {status_icon:<6}")

    avg_time = total_time_ms / total_tests

    print("=" * 80)
    print("ISTATISTIKSEL BASARIM OZETI (ACCURACY METRICS):")
    print("=" * 80)
    print(f"* 2 Haneli Fasıl Doğruluğu (Chapter Accuracy) : %{(match_2digit / total_tests) * 100:.1f}")
    print(f"* 4 Haneli Pozisyon Doğruluğu (Heading Acc.)  : %{(match_4digit / total_tests) * 100:.1f}")
    print(f"* 6 Haneli HS Kodu Doğruluğu (HS Code Acc.)   : %{(match_6digit / total_tests) * 100:.1f}")
    print(f"* 12 Haneli Tam GTİP Doğruluğu (12-Digit Acc.): %{(match_12digit / total_tests) * 100:.1f}")
    print(f"* Ortalama Analiz Yanıt Süresi               : {avg_time:.2f} ms")
    print("=" * 80)

if __name__ == "__main__":
    run_accuracy_evaluation()
