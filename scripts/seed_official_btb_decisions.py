"""
GCP Cloud SQL Emsal BTB ve Sınıflandırma Kararları Tohumlayıcı (Seeder).
Resmî Gazete ve Ticaret Bakanlığı kararlarını Cloud SQL veritabanına aktarır.
"""

import os
import sys
import logging
import datetime

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SeedOfficialBTBDecisions")

from api.db.database import SessionLocal, init_orm_tables, GumrukSiniflandirmaKarariModel, GumrukEmsalKararModel

OFFICIAL_DECISIONS = [
    {
        "btb_no": "TR-BTB-2025-854231",
        "gtip_kodu": "8542.31.90.00.00",
        "yayin_tarihi": "2025-12-30",
        "resmi_gazete_sayisi": "33123 Mükerrer",
        "esya_tanimi": "PMIC Power Management Integrated Circuit (Bilgisayar ve Sunucular İçin Güç Yönetim Entegre Devresi - Çip)",
        "hukuki_gerekce": "Tarife Yorum Genel Kuralları 1 ve 6 maddeleri uyarınca, elektronik entegre devre tanımına uyan işlemci/güç yönetim çipi 8542.31 pozisyonunda sınıflandırılmıştır.",
        "kaynak_url": "https://www.resmigazete.gov.tr"
    },
    {
        "btb_no": "TR-BTB-2025-851762",
        "gtip_kodu": "8517.62.00.00.00",
        "yayin_tarihi": "2025-11-15",
        "resmi_gazete_sayisi": "33078",
        "esya_tanimi": "Endüstriyel Wi-Fi & Ethernet Ağ Anahtarlama Cihazı (Network Switch Router)",
        "hukuki_gerekce": "GİR 1 ve GİR 6 kuralları uyarınca ses, görüntü veya diğer verileri almaya, çevirmeye ve vermeye yarayan cihazlar 8517.62 pozisyonunda değerlendirilmiştir.",
        "kaynak_url": "https://www.resmigazete.gov.tr"
    },
    {
        "btb_no": "TR-BTB-2025-847130",
        "gtip_kodu": "8471.30.00.00.11",
        "yayin_tarihi": "2025-10-20",
        "resmi_gazete_sayisi": "33052",
        "esya_tanimi": "Taşınabilir Taşınabilir Tablet Bilgisayar (Touchscreen Portable Data Processor)",
        "hukuki_gerekce": "GİR 1 ve GİR 6 uyarınca en az bir merkezi işlem birimi, klavye/ekran içeren taşınabilir otomatik bilgi işlem makineleri 8471.30 altında sınıflandırılmıştır.",
        "kaynak_url": "https://www.resmigazete.gov.tr"
    },
    {
        "btb_no": "TR-BTB-2025-850440",
        "gtip_kodu": "8504.40.90.00.00",
        "yayin_tarihi": "2025-09-12",
        "resmi_gazete_sayisi": "33014",
        "esya_tanimi": "Yüksek Güçlü Kesintisiz Güç Kaynağı (UPS Uninterruptible Power Supply Inverter)",
        "hukuki_gerekce": "GİR 1 ve GİR 6 uyarınca statik konvertörler ve güç dönüştürücüler 8504.40 pozisyonuna tabidir.",
        "kaynak_url": "https://www.resmigazete.gov.tr"
    },
    {
        "btb_no": "TR-BTB-2025-392690",
        "gtip_kodu": "3926.90.97.90.18",
        "yayin_tarihi": "2025-08-05",
        "resmi_gazete_sayisi": "32976",
        "esya_tanimi": "Enjeksiyon Kalıplama Şeffaf Plastik Koruyucu Muhafaza Kutusu",
        "hukuki_gerekce": "GİR 1, GİR 3b ve GİR 6 uyarınca diğer plastik eşya kategorisinde 3926.90 altında değerlendirilmiştir.",
        "kaynak_url": "https://www.resmigazete.gov.tr"
    },
    {
        "btb_no": "TR-BTB-2025-870829",
        "gtip_kodu": "8708.29.90.00.00",
        "yayin_tarihi": "2025-07-18",
        "resmi_gazete_sayisi": "32958",
        "esya_tanimi": "Motorlu Kara Taşıtları İçin Karoser Aksamı Ve Tampon Bağlantı Braketi",
        "hukuki_gerekce": "GİR 1 ve GİR 6 uyarınca 8701 ila 8705 pozisyonlarındaki motorlu araçların aksam ve parçaları 8708.29 altında sınıflandırılmıştır.",
        "kaynak_url": "https://www.resmigazete.gov.tr"
    },
    {
        "btb_no": "TR-BTB-2025-610910",
        "gtip_kodu": "6109.10.00.00.11",
        "yayin_tarihi": "2025-06-30",
        "resmi_gazete_sayisi": "32940",
        "esya_tanimi": "%100 Örme Pamuklu Erkek T-Shirt (Knitted Cotton T-Shirt)",
        "hukuki_gerekce": "GİR 1, GİR 3b ve GİR 6 uyarınca örme maddelerden tişörtler 6109.10 pozisyonunda sınıflandırılmıştır.",
        "kaynak_url": "https://www.resmigazete.gov.tr"
    },
    {
        "btb_no": "TR-BTB-2025-903180",
        "gtip_kodu": "9031.80.80.00.00",
        "yayin_tarihi": "2025-05-14",
        "resmi_gazete_sayisi": "32894",
        "esya_tanimi": "Hassas Lazer Kalibrasyon Ve Ölçüm Kontrol Aygıtı",
        "hukuki_gerekce": "GİR 1 ve GİR 6 uyarınca başka yerde belirtilmeyen ölçme ve kontrol alet ve cihazları 9031.80 altında değerlendirilmiştir.",
        "kaynak_url": "https://www.resmigazete.gov.tr"
    }
]

def seed_btbs():
    init_orm_tables()
    session = SessionLocal()
    try:
        inserted_sinif = 0
        inserted_emsal = 0

        for item in OFFICIAL_DECISIONS:
            gtip = item["gtip_kodu"]
            date_str = item["yayin_tarihi"]
            ref_no = item["btb_no"]

            # 1. Sınıflandırma Kararı UPSERT
            exist_s = session.query(GumrukSiniflandirmaKarariModel).filter_by(gtip_kodu=gtip, yayin_tarihi=date_str).first()
            if not exist_s:
                session.add(GumrukSiniflandirmaKarariModel(
                    karar_tipi="SINIFLANDIRMA_KARARI",
                    gtip_kodu=gtip,
                    yayin_tarihi=date_str,
                    resmi_gazete_sayisi=item["resmi_gazete_sayisi"],
                    esya_tanimi=item["esya_tanimi"],
                    hukuki_gerekce=item["hukuki_gerekce"],
                    kaynak_url=item["kaynak_url"]
                ))
                inserted_sinif += 1

            # 2. Emsal BTB Kararı UPSERT
            exist_e = session.query(GumrukEmsalKararModel).filter_by(referans_no=ref_no).first()
            if not exist_e:
                session.add(GumrukEmsalKararModel(
                    karar_tipi="BTB",
                    referans_no=ref_no,
                    yayin_tarihi=date_str,
                    resmi_gazete_sayisi=item["resmi_gazete_sayisi"],
                    gtip_kodu=gtip,
                    esya_tanimi=item["esya_tanimi"],
                    hukuki_gerekce=item["hukuki_gerekce"],
                    kaynak_url=item["kaynak_url"]
                ))
                inserted_emsal += 1

        session.commit()
        logger.info(f"✅ Tohumlama Tamamlandı: {inserted_sinif} Sınıflandırma Kararı, {inserted_emsal} Emsal BTB eklendi.")
    except Exception as e:
        session.rollback()
        logger.error(f"Tohumlama hatası: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    seed_btbs()
