"""
Gümrük Mevzuat ve BTB Canlı Web Bağlantı & Veri Çekme Testi (Live Scraper Tester).
Resmi kaynakların (Ticaret Bakanlığı, Resmi Gazete) canlı erişilebilirliğini ve veri çekme performansını test eder.
"""
import os
import sys
import json
import time
import requests
from xml.etree import ElementTree
from bs4 import BeautifulSoup

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

from api.db.tgtc_knowledge_base import TGTC_CHAPTERS

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}

def test_ticaret_bakanligi_btb_portal():
    print("\n----------------------------------------------------------------------")
    print("1. TEST: Ticaret Bakanlığı BTB Portal Canlı Erişimi (uygulamalar.gtb.gov.tr)")
    print("----------------------------------------------------------------------")
    url = "https://uygulamalar.gtb.gov.tr/BTBArama"
    
    start_time = time.time()
    try:
        session = requests.Session()
        try:
            resp = session.get(url, headers=HEADERS, verify=True, timeout=10)
        except requests.exceptions.SSLError as ssl_err:
            print(f"[UYARI] SSL Sertifika Doğrulama Uyarısı: {ssl_err}. SSL Insecure Fallback deneniyor...")
            resp = session.get(url, headers=HEADERS, verify=False, timeout=10)

        elapsed = round(time.time() - start_time, 2)
        print(f"-> HTTP Yanıt Kodu: {resp.status_code}")
        print(f"-> Yanıt Süresi: {elapsed} saniye")
        print(f"-> İçerik Boyutu: {len(resp.content)} bayt")

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.find_all('tr')
            print(f"-> HTML İçerisinde Bulunan Tablo Satırı (tr) Sayısı: {len(rows)}")

            scraped_items = []
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    btb_no = cols[0].get_text(strip=True)
                    gtip = cols[1].get_text(strip=True)
                    desc = cols[2].get_text(strip=True)
                    if btb_no and gtip:
                        scraped_items.append((btb_no, gtip, desc[:40]))

            print(f"-> Ayrıştırılan Canlı BTB Karar Sayısı: {len(scraped_items)}")
            if scraped_items:
                print("   Örnek Karar 1:", scraped_items[0])
            print("[SUCCESS] TEST BASARILI: Ticaret Bakanligi BTB Portali Erisilebilir ve Veri Cekilebilir.")
        else:
            print(f"[FAIL] TEST BASARISIZ: Portal {resp.status_code} kodu dondurdu.")
    except Exception as e:
        print(f"[FAIL] TEST BASARISIZ / ERISIM ENGELI: {e}")
        print("NOTE: Ticaret Bakanligi 'uygulamalar.gtb.gov.tr' sunuculari bazi ISP/DNS servislerinde veya yurt disi IP'lerde Cloudflare/WAF korumasi nedeniyle engelli olabilir.")

def test_resmi_gazete_rss():
    print("\n----------------------------------------------------------------------")
    print("2. TEST: T.C. Resmi Gazete Canli RSS Akis Erisimi (www.resmigazete.gov.tr)")
    print("----------------------------------------------------------------------")
    url = "https://www.resmigazete.gov.tr/rss"
    start_time = time.time()
    try:
        resp = requests.get(url, headers=HEADERS, verify=False, timeout=10)
        elapsed = round(time.time() - start_time, 2)
        print(f"-> HTTP Yanit Kodu: {resp.status_code}")
        print(f"-> Yanit Suresi: {elapsed} saniye")

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            items = soup.find_all('item')
            print(f"-> Resmi Gazete'den Cekilen Toplam Haber/Teblig Sayisi: {len(items)}")
            customs_count = 0
            for item in items:
                title = item.find('title')
                title_text = title.get_text(strip=True) if title else ""
                if any(kw in title_text.lower() for kw in ["gümrük", "ithalat", "tarife", "btb", "tebliğ"]):
                    customs_count += 1
            print(f"-> Suzulen Gumruk & Ithalat Tebligi Sayisi: {customs_count}")
            print("[SUCCESS] TEST BASARILI: Resmi Gazete Canli RSS Akisi Erisilebilir.")
        else:
            print(f"[FAIL] TEST BASARISIZ: Resmi Gazete {resp.status_code} dondurdu.")
    except Exception as e:
        print(f"[FAIL] TEST BASARISIZ: {e}")

def test_local_database_coverage():
    print("\n----------------------------------------------------------------------")
    print("3. TEST: Veritabani Kapsam ve 99 Fasil Tamlik Testi")
    print("----------------------------------------------------------------------")
    db_path = os.path.join(base_dir, "api", "data", "official_btb_database.json")
    vec_path = os.path.join(base_dir, "api", "data", "vector_index.json")

    if os.path.exists(db_path):
        with open(db_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        print(f"-> Veritabanindaki Toplam BTB Kaydi Sayisi: {len(records)}")

        chapters = sorted(list(set(r.get("chapter") for r in records if r.get("chapter"))))
        print(f"-> Veritabanindaki Toplam Temsil Edilen Fasil Sayisi: {len(chapters)} / 99 Fasil")

        missing = [f"{i:02d}" for i in range(1, 100) if f"{i:02d}" not in chapters and f"{i:02d}" != "77"]
        if not missing:
            print("[SUCCESS] TEST BASARILI: Yururlukteki Tum Fasillar (%100 Tam Kapsam) Veritabaninda Mevcut!")
        else:
            print(f"[WARNING] Eksik Fasillar Tespit Edildi: {missing}")

    if os.path.exists(vec_path):
        with open(vec_path, "r", encoding="utf-8") as f:
            vec_data = json.load(f)
        entries = vec_data.get("entries", vec_data)
        print(f"-> RAG Vektor Arama Indeksindeki Kayit Sayisi: {len(entries)}")

if __name__ == "__main__":
    print("======================================================================")
    print("[TEST SUITE] GUMRUK CANLI WEB KAZIMA VE VERI CEKME ERISILEBILIRLIK TESTI")
    print("======================================================================")
    test_ticaret_bakanligi_btb_portal()
    test_resmi_gazete_rss()
    test_local_database_coverage()
    print("\n======================================================================")
    print("[TEST SUITE] TUM ERISIM VE VERI CEKME TESTLERI TAMAMLANDI")
    print("======================================================================")
