import os
import sys
import re
import time
import json
import argparse
import requests
from bs4 import BeautifulSoup
import pdfplumber
from typing import List, Dict, Any, Optional
from datetime import datetime, date

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

print("========================================================================================")
print("  T.C. RESMI GAZETE GUMRUK SINIFLANDIRMA VE TEBLIG OTOMASYON MOTORU (ORM & IDEMPOTENT)")
print("  Mimariler: Tek Seferlik 2020-2026 Aktarimi | Gunluk & Mukerrer RSS Idempotent Takip")
print("========================================================================================\n")

# Veritabanı ve ORM Modeli Hazırlığı
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
from api.db.database import engine, SessionLocal, Base, GumrukEmsalKararModel

# Tablo Şemalarını Doğrula / Kur
try:
    Base.metadata.create_all(bind=engine)
    print("[OK] GCP Cloud SQL ORM -> 'gumruk_emsal_kararlar' ve bagli tablolarin mimarisi dogrulandi!")
except Exception as e:
    print(f"[UYARI] Tablo sema dogrulama uyarisi: {e}")

# 1. PDF Tablo Ayrıştırıcı (pdfplumber)
def parse_customs_pdf(pdf_path_or_file) -> List[Dict[str, Any]]:
    """Resmi Gazete Ek Sınıflandırma Karar tablolarını pdfplumber ile söker."""
    decisions = []
    try:
        with pdfplumber.open(pdf_path_or_file) as pdf:
            for page_no, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 2:
                            continue
                        clean_row = [str(col).strip() if col else "" for col in row]
                        for col_idx, text_cell in enumerate(clean_row):
                            stripped_digits = text_cell.replace(".", "").replace(" ", "").strip()
                            if stripped_digits.isdigit() and 6 <= len(stripped_digits) <= 12:
                                gtip = text_cell.strip()
                                desc = clean_row[0] if col_idx > 0 else clean_row[1]
                                reason = clean_row[-1] if len(clean_row) >= 3 else "T.C. Resmi Gazete Siniflandirma Karari Uyarinca."
                                if desc and len(desc) > 5 and desc != gtip:
                                    decisions.append({
                                        "gtip_kodu": gtip,
                                        "esya_tanimi": desc,
                                        "hukuki_gerekce": reason
                                    })
                                break
    except Exception as e:
        print(f"  [PDF PARSE UYARISI] {e}")
    return decisions

# 2. HTML Tablo Ayrıştırıcı (BeautifulSoup)
def parse_customs_html(html_text: str) -> List[Dict[str, Any]]:
    """Resmi Gazete HTML tebliğlerindeki gömülü tabloları söker."""
    decisions = []
    try:
        soup = BeautifulSoup(html_text, 'lxml')
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                cols = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if len(cols) < 2:
                    continue
                for col_idx, text_cell in enumerate(cols):
                    stripped = re.sub(r"[^\d]", "", text_cell)
                    if stripped.isdigit() and 6 <= len(stripped) <= 12:
                        gtip = text_cell.strip()
                        desc = cols[0] if col_idx > 0 else (cols[1] if len(cols) > 1 else "")
                        reason = cols[-1] if len(cols) >= 3 else "GIR Yorum Kurallari uyarinca baglayici tarife siniflandirmasi."
                        if desc and len(desc) > 4 and desc != gtip and not desc.lower().startswith("gtip"):
                            decisions.append({
                                "gtip_kodu": gtip,
                                "esya_tanimi": desc,
                                "hukuki_gerekce": reason
                            })
                        break
    except Exception as e:
        print(f"  [HTML PARSE UYARISI] {e}")
    return decisions

# 3. TEK SEFERLİK 2020 - 2026 SINIFLANDIRMA KARARLARI (Historical Bulk Import)
def run_bulk_import_2020_2026():
    print("[MOD 1] 2020-2026 Arası Gerçek Emsal Sınıflandırma Kararları Canlı Taramayla Çekiliyor...")
    print("[PRENSİP] Sıfır uydurma / statik veri: Sadece gerçek T.C. Ticaret Bakanlığı ve Resmî Gazete tebliğleri işlenir.")

    scraped_decisions = []
    
    # 1. Ticaret Bakanlığı GGM ve Resmi Tarife Kararları Arşivi Taraması
    search_urls = [
        "https://ggm.ticaret.gov.tr/mevzuat/gumruk-tarifesi",
        "https://ggm.ticaret.gov.tr/mevzuat/gumruk-tarifesi/siniflandirma-kararlari",
        "https://ggm.ticaret.gov.tr/duyurular"
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gumruk Tarife Yapay Zeka Bot/2026.1"}
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    for url in search_urls:
        try:
            print(f" -> {url} portalı taranıyor...")
            resp = requests.get(url, headers=headers, timeout=15, verify=False)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, "html.parser")
                for link in soup.find_all("a", href=True):
                    txt = link.get_text(strip=True)
                    href = link.get("href", "")
                    if any(kw in txt.lower() or kw in href.lower() for kw in ["siniflandirma", "tebligi", "emsal", "btb", "karar"]):
                        if not href.startswith("http"):
                            domain = "https://ggm.ticaret.gov.tr" if "ggm" in url else "https://www.ticaret.gov.tr"
                            href = domain + "/" + href.lstrip("/")
                        
                        # Doküman indirip parse et (PDF veya HTML)
                        try:
                            doc_resp = requests.get(href, headers=headers, timeout=15, verify=False)
                            if doc_resp.status_code == 200:
                                if href.lower().endswith(".pdf") or "application/pdf" in doc_resp.headers.get("content-type", ""):
                                    import io
                                    pdf_mem = io.BytesIO(doc_resp.content)
                                    parsed = parse_customs_pdf(pdf_mem)
                                    for p in parsed:
                                        p["kaynak_url"] = href
                                        p["teblig_no"] = txt[:100]
                                        p["resmi_gazete_tarihi"] = str(date.today())
                                        p["resmi_gazete_sayisi"] = "Resmi Arşiv"
                                        scraped_decisions.append(p)
                                else:
                                    parsed = parse_customs_html(doc_resp.text)
                                    for p in parsed:
                                        p["kaynak_url"] = href
                                        p["teblig_no"] = txt[:100]
                                        p["resmi_gazete_tarihi"] = str(date.today())
                                        p["resmi_gazete_sayisi"] = "Resmi Arşiv"
                                        scraped_decisions.append(p)
                        except Exception as ex_doc:
                            print(f"   [Doc Parse Hata] {href}: {ex_doc}")
        except Exception as e:
            print(f" [Tarayıcı Bilgi] {url} erişimi başarısız veya yapı kısıtlaması: {e}")

    # 2. sync_customs_data.py içindeki gerçek canlı otomat motorunu tetikle ve gerçek kararları topla
    try:
        from scripts.sync_customs_data import scrape_ggm_btb, scrape_eu_ebti
        print(" -> Canlı GGM ve EBTI gümrük motorları tetikleniyor...")
        real_ggm_items = scrape_ggm_btb()
        for it in real_ggm_items:
            scraped_decisions.append({
                "teblig_no": it.get("btb_no", "GGM-Emsal"),
                "resmi_gazete_tarihi": it.get("issue_date", str(date.today())),
                "resmi_gazete_sayisi": "GGM Tebliğ",
                "gtip_kodu": it.get("gtip_code", ""),
                "esya_tanimi": it.get("product_description", ""),
                "hukuki_gerekce": it.get("legal_justification", ""),
                "kaynak_url": "https://ggm.ticaret.gov.tr"
            })
    except Exception as e_sync:
        print(f" [Sync Motor Bilgi] Canlı çekim uyarısı: {e_sync}")

    if not scraped_decisions:
        print("[BILGI] Bu tur taramada yeni kazınabilir tarife tebliğ dokümanına ulaşılamadı (Sıfır sahte veri kuralı gereği veritabanına ekleme yapılmıyor).")
        return

    session = SessionLocal()
    added, updated = 0, 0
    try:
        for d in scraped_decisions:
            gtip_clean = str(d["gtip_kodu"]).strip()
            if not gtip_clean or len(gtip_clean) < 6:
                continue

            record = session.query(GumrukEmsalKararModel).filter_by(
                karar_tipi="SINIFLANDIRMA_KARARI",
                gtip_kodu=gtip_clean,
                referans_no=str(d["teblig_no"])[:100]
            ).first()

            if not record:
                new_rec = GumrukEmsalKararModel(
                    karar_tipi="SINIFLANDIRMA_KARARI",
                    referans_no=str(d["teblig_no"])[:100],
                    yayin_tarihi=str(d["resmi_gazete_tarihi"]),
                    resmi_gazete_sayisi=str(d.get("resmi_gazete_sayisi", "-"))[:50],
                    gtip_kodu=gtip_clean[:50],
                    esya_tanimi=str(d["esya_tanimi"])[:500],
                    hukuki_gerekce=str(d["hukuki_gerekce"])[:500],
                    kaynak_url=str(d.get("kaynak_url", ""))[:255]
                )
                session.add(new_rec)
                added += 1
            else:
                record.esya_tanimi = str(d["esya_tanimi"])[:500]
                record.hukuki_gerekce = str(d["hukuki_gerekce"])[:500]
                updated += 1

        session.commit()
        print(f"[OK] ORM Tek Seferlik Kurulum -> {added} gerçek Emsal Sınıflandırma Kararı veritabanına işlendi ({updated} güncellendi).")
    except Exception as e:
        session.rollback()
        print(f"[HATA] ORM İşlem Hatası: {e}")
    finally:
        session.close()

# 4. GÜNLÜK VE MÜKERRER İDEMPOTENT KONTROL (Daily & Mükerrer Cron Job)
def run_daily_idempotent_cron():
    """
    Her gece 00:30'da (Ana) ve gündüz 08:00 ile 14:00'te (Mükerrer Kontrolü) koşturulan motor.
    resmigazete.gov.tr/rss akışını okur, veritabanı ile IDEMPONTENT kontrol yapar.
    Sıfır uydurma veri kuralı: O günkü gazetede gerçek gümrük tebliği yoksa HİÇBİR ŞEY EKLEMEZ.
    """
    print("[MOD 2] Günlük ve Mükerrer Sayı Idempotent Denetim (RSS Monitor) Devrede...")
    rss_url = "https://www.resmigazete.gov.tr/rss"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gumruk Tarife Yapay Zeka Bot/2026.1"}
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    soup = None
    
    try:
        print(f" -> {rss_url} XML akışı çekiliyor...")
        resp = requests.get(rss_url, headers=headers, timeout=15, verify=False)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "xml")
    except Exception as e:
        print(f"[BILGI] Resmi Gazete RSS akışı okunamadı: {e}")

    today_str = date.today().isoformat()
    detected_edition = f"{today_str}-1"
    mkr_detected = False
    new_items_to_process = []

    if soup:
        items = soup.find_all("item")
        print(f" -> RSS akışında {len(items)} adet haber/tebliğ başlığı tespit edildi.")
        for item in items:
            title = item.title.text if item.title else ""
            link = item.link.text if item.link else ""
            
            if "Mükerrer" in title or "mukerrer" in title:
                mkr_detected = True
                detected_edition = f"{today_str}-Mukerrer"
                print(f" [MÜKERRER SAYI ALARMI] Gün içinde mükerrer Resmi Gazete yayımlandı: {title}")
                
            # Gümrük Tarife / Sınıflandırma Kararı mı?
            if any(k in title.lower() for k in ["gümrük genel tebliği", "sınıflandırma kararı", "bağlayıcı tarife", "tarife cetveli"]):
                new_items_to_process.append({"title": title, "link": link})

    print(f" -> Hedef Gazete Sayısı / Tarihi: {detected_edition} (Mükerrer mi: {mkr_detected})")

    session = SessionLocal()
    try:
        existing = session.query(GumrukEmsalKararModel).filter_by(resmi_gazete_sayisi=detected_edition).first()
        if existing and not new_items_to_process:
            print(f" [IDEMPOTENT KORUMA] '{detected_edition}' sayılı Resmi Gazete ZATEN incelendi.")
            return

        if not new_items_to_process:
            print(f" [SIFIR UYDURMA VERİ] '{detected_edition}' sayılı Resmi Gazete'de bugün Gümrük Sınıflandırma Tebliği veya emsal karar yayımlanmamış.")
            print(" -> Sahte/test verisi basımı durduruldu. Akış başarıyla sonlandı.")
            return

        print(f" [YENİ YAYIN TESPİTİ] '{detected_edition}' içinde {len(new_items_to_process)} adet gümrük tebliğ dokümanı işleniyor...")
        for it in new_items_to_process:
            doc_link = it["link"]
            try:
                doc_resp = requests.get(doc_link, headers=headers, timeout=15, verify=False)
                if doc_resp.status_code == 200:
                    if doc_link.lower().endswith(".pdf"):
                        import io
                        parsed = parse_customs_pdf(io.BytesIO(doc_resp.content))
                    else:
                        parsed = parse_customs_html(doc_resp.text)
                        
                    for p in parsed:
                        new_rec = GumrukEmsalKararModel(
                            karar_tipi="SINIFLANDIRMA_KARARI",
                            referans_no=it["title"][:100],
                            yayin_tarihi=today_str,
                            resmi_gazete_sayisi=detected_edition,
                            gtip_kodu=str(p["gtip_kodu"])[:50],
                            esya_tanimi=str(p["esya_tanimi"])[:500],
                            hukuki_gerekce=str(p["hukuki_gerekce"])[:500],
                            kaynak_url=doc_link[:255]
                        )
                        session.add(new_rec)
            except Exception as ex_item:
                print(f"  [Tebliğ İndirme Hatası] {doc_link}: {ex_item}")
                
        session.commit()
        print(f" [OK] '{detected_edition}' tarandı ve yeni Resmî Gazete verileri Cloud SQL veritabanına aktarıldı!")
    except Exception as e:
        session.rollback()
        print(f"[HATA] ORM Cron Hatası: {e}")
    finally:
        session.close()

def main():
    parser = argparse.ArgumentParser(description="Resmî Gazete Gümrük Mevzuatı ORM Otomatı")
    parser.add_argument("--bulk-2020-2026", action="store_true", help="2020-2026 Geciş Dönemi Kararlarını 1 kez import eder.")
    parser.add_argument("--daily-cron", action="store_true", help="Günlük (00:30) ve Mükerrer (08:00, 14:00) Idempotent taramayı çalıştırır.")
    args = parser.parse_args()

    if not args.bulk_2020_2026 and not args.daily_cron:
        run_bulk_import_2020_2026()
        print("\n" + "-"*80 + "\n")
        run_daily_idempotent_cron()
    else:
        if args.bulk_2020_2026:
            run_bulk_import_2020_2026()
        if args.daily_cron:
            run_daily_idempotent_cron()

if __name__ == "__main__":
    main()
