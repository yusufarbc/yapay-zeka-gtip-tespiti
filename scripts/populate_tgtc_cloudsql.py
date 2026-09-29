import os
import sys
import json
from sqlalchemy.orm import Session
from sqlalchemy import text

# Add the project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.db.database import engine, init_orm_tables, TgtcRuleModel, TgtcNoteModel, TgtcGtipModel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TGTC_DIR = os.path.join(BASE_DIR, "2026 TGTC")

def clean_turkish(text_input):
    if not isinstance(text_input, str):
        return ""
    # Remove weird zero-width spaces or unexpected bytes if any
    return text_input.strip()

def extract_gir_rules(session: Session):
    print("Extracting GİR Rules...")
    
    session.query(TgtcRuleModel).filter_by(rule_type="GIR").delete()
    session.commit()

    rules = [
        {"rule_number": "1", "title": "GİR Kuralı 1 - Pozisyon Metinleri ve Bölüm/Fasıl Notları", "text": "Bölüm, fasıl ve tali fasıl başlıkları sadece gösterici niteliktedir; yasal amaçlar için eşyanın tarifedeki yerinin saptanması, pozisyon metinlerine, ilgili herhangi bir bölüm veya fasıl notuna ve bu pozisyonlar veya notlar hükümlerinde aksi belirtilmedikçe, aşağıdaki kurallara göre yapılır."},
        {"rule_number": "2(a)", "title": "GİR Kuralı 2(a) - Tamamlanmamış veya Birleştirilmemiş Eşya", "text": "Tarifenin belirli bir pozisyonunda herhangi bir eşyaya yapılan bir atıf, bu eşyanın imali bitirilmemiş veya aksamı tamamlanmamış olanlarını da kapsar. Şu şartla ki, eşyanın gümrüğe sunulduğunda, imali bitirilmiş veya aksamı tamamlanmış eşyanın ayırt edici niteliğini içermesi gerekir. Keza, bir eşyaya yapılan atıf, imali bitirilmiş veya aksamı tamamlanmış eşya ile yukarıdaki hüküm gereğince böyle sayılan eşyanın sökük veya monte edilmemiş halde olanlarını da kapsar."},
        {"rule_number": "2(b)", "title": "GİR Kuralı 2(b) - Karışım veya Bileşimler", "text": "Tarifenin belirli bir pozisyonunda herhangi bir maddeye yapılan atıf, bu maddenin diğer maddelerle karışım veya bileşimlerini de içine alır. Aynı şekilde, belirli bir maddeden mamul bir eşyaya yapılan atıf, tamamen veya kısmen bu maddeden mamul eşyayı da kapsar. Birden fazla maddeden mamul eşyanın tarifedeki yeri 3 nolu kural prensiplerine göre saptanır."},
        {"rule_number": "3(a)", "title": "GİR Kuralı 3(a) - Özel Pozisyon Önceliği", "text": "2(b) kuralının uygulanması veya başka bir nedenle eşyanın, ilk bakışta iki veya daha fazla pozisyonda sınıflandırılabileceği izlenimini vermesi halinde tarifedeki yeri aşağıdaki şekilde saptanır:\n(a) Eşyayı en özel şekilde tanımlayan pozisyon, daha genel şekilde tanımlayan pozisyona göre öncelik alır. Bununla beraber, iki veya daha fazla pozisyonun her biri, karışım veya bileşim halindeki maddelerin sadece bir kısmına veya perakende satılacak hale getirilmiş takım halindeki eşyanın sadece bir parçasına atıfta bulunuyorsa; bu pozisyonlar, içlerinden biri eşyayı daha tam ve kesin olarak tanımlasa bile, söz konusu eşya bakımından eşit derecede özel sayılır."},
        {"rule_number": "3(b)", "title": "GİR Kuralı 3(b) - Esas Özelliği Veren Madde", "text": "(b) 3(a) kuralının uygulanmasıyla tarifedeki yeri saptanamayan karışımlar, farklı maddelerden müteşekkil veya farklı parçalardan birleşmiş eşya ve perakende satılacak hale getirilmiş takım halindeki eşya, uygulanabilmesi mümkün olduğu takdirde, eşyaya esas özelliğini veren madde veya parçaya göre sınıflandırılır."},
        {"rule_number": "3(c)", "title": "GİR Kuralı 3(c) - Son Pozisyon", "text": "(c) 3(a) veya 3(b) kurallarının uygulanmasıyla tarifedeki yeri saptanamayan eşya, sırasıyla uygulanabilecek pozisyonların numara sırasına göre en sonuncusunda sınıflandırılır."},
        {"rule_number": "4", "title": "GİR Kuralı 4 - En Çok Benzeyen Eşya", "text": "Yukarıdaki kurallara göre sınıflandırılamayan eşya, kendisine en çok benzeyen eşyanın bulunduğu pozisyonda sınıflandırılır."},
        {"rule_number": "5(a)", "title": "GİR Kuralı 5(a) - Kılıflar ve Muhafazalar", "text": "Aşağıdaki kurallar yukarıdaki hükümlere ilaveten, sadece bu kurallarda belirtilen eşyaya uygulanır:\n(a) Fotoğraf makinesi muhafazası, müzik aleti mahfazası, silah kılıfı, çizim aleti kutusu, kolye kutusu ve benzeri kaplar, özellikle ait oldukları eşyayı veya takımı alacak şekilde şekillendirilmiş veya bu eşyaya uygun olarak yapılmış olup, uzun süre kullanılmaya müsait olan ve ait oldukları eşya ile birlikte ithal edilen ve normal olarak onlarla birlikte satılan türden iseler, beraber satıldıkları eşya ile birlikte sınıflandırılırlar. Bununla beraber, bu kural, bütününe esas özelliğini veren kaplara uygulanmaz."},
        {"rule_number": "5(b)", "title": "GİR Kuralı 5(b) - Ambalaj Maddeleri", "text": "(b) 5(a) kuralı hükümleri saklı kalmak şartıyla, içindeki eşya ile birlikte sunulan ambalaj maddeleri ve ambalaj kapları, bu tür eşyanın ambalajında normal olarak kullanıldıkları takdirde o eşya ile beraber sınıflandırılırlar. Ancak, bu kural, sürekli kullanıma elverişli oldukları açıkça belli olan ambalaj maddeleri ve ambalaj kapları için zorunlu değildir."},
        {"rule_number": "6", "title": "GİR Kuralı 6 - Alt Pozisyon Kuralı", "text": "Yasal amaçlar için eşyanın herhangi bir pozisyonun alt pozisyonlarında sınıflandırılması, sadece aynı seviyedeki alt pozisyonların mukayese edilebilirliği şartıyla, alt pozisyon metinlerine ve bu alt pozisyonların notlarına ve gerekli değişiklikler yapılmış olarak yukarıdaki kurallara göre saptanır. Aksine bir hüküm yoksa, bu kuralın uygulanmasında ilgili bölüm ve fasıl notları da dikkate alınır."}
    ]

    for r in rules:
        obj = TgtcRuleModel(
            rule_type="GIR",
            rule_number=r["rule_number"],
            title=r["title"],
            text=r["text"]
        )
        session.add(obj)
    
    session.commit()
    print("GİR Rules inserted.")

def _rules_and_notes() -> dict:
    """Resmî TGTC ekleri (yorum kuralları, ölçü birimleri, 96 fasıl notu).

    Ham Excel dosyaları repodan kaldırıldı; aynı içerik bu JSON'dadır ve
    sınıflandırma fasıl notlarını zaten buradan okur (api/modules/tariff_notes.py).
    """
    path = os.path.join(TGTC_DIR, "tgtc_2026_rules_and_notes.json")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_measurements(session: Session):
    print("Extracting Measurements...")
    if session.query(TgtcRuleModel).filter_by(rule_type="MEASUREMENT").count() > 0:
        print("Measurements already exist in DB. Skipping.")
        return
    lines = [str(line).strip() for line in _rules_and_notes().get("olcu_birimleri", []) if str(line).strip()]
    for idx, val in enumerate(lines):
        session.add(TgtcRuleModel(
            rule_type="MEASUREMENT",
            rule_number=str(idx + 1),
            title="Ölçü Birimi" if idx == 0 else f"Ölçü Birimi {idx}",
            text=val,
        ))
    session.commit()
    print("Measurements inserted.")


def extract_chapter_notes(session: Session):
    print("Extracting Chapter Notes...")
    session.query(TgtcNoteModel).delete()
    session.commit()

    for chapter, raw_text in _rules_and_notes().get("fasil_notlari", {}).items():
        try:
            chapter_code = f"{int(str(chapter)):02d}"
        except ValueError:
            continue
        text_val = str(raw_text or "").strip()
        if text_val:
            session.add(TgtcNoteModel(chapter_code=chapter_code, text=text_val))

    session.commit()
    print("Chapter Notes inserted.")

def populate_gtip_tree(session: Session):
    print("Populating GTİP Tree...")
    session.query(TgtcGtipModel).delete()
    session.commit()
        
    json_path = os.path.join(TGTC_DIR, "tgtc_2026_full_database.json")
    if not os.path.exists(json_path):
        print(f"Could not find {json_path}")
        return

    notes_json_path = os.path.join(TGTC_DIR, "tgtc_2026_rules_and_notes.json")
    chapter_titles = {}
    if os.path.exists(notes_json_path):
        try:
            with open(notes_json_path, "r", encoding="utf-8") as nf:
                ndata = json.load(nf)
                f_notes = ndata.get("fasil_notlari", {})
                for c_code, raw_text in f_notes.items():
                    lines = [l.strip() for l in str(raw_text).split('\n') if l.strip()]
                    t_val = f"Fasıl {c_code}"
                    for line in lines:
                        if 'FASIL' in line.upper() or 'BÖLÜM' in line.upper():
                            continue
                        if 'NOT' in line.upper():
                            break
                        t_val = line
                        break
                    chapter_titles[c_code.zfill(2)] = t_val
        except Exception as ex:
            print(f"Error extracting chapter titles: {ex}")

    existing_codes = set(r[0] for r in session.query(TgtcGtipModel.gtip_code).all())

    # Insert chapters 01..99
    inserted_count = 0
    for c_i in range(1, 100):
        c_str = str(c_i).zfill(2)
        c_title = chapter_titles.get(c_str, f"Fasıl {c_str}")
        if c_str not in existing_codes:
            session.add(TgtcGtipModel(
                gtip_code=c_str,
                level="CHAPTER",
                parent_code=None,
                description=c_title,
                is_active=True
            ))
            existing_codes.add(c_str)
            inserted_count += 1
    session.commit()
    print(f"Inserted {inserted_count} CHAPTER entries.")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for entry in data:
        code_raw = str(entry.get("gtip_code", "")).strip()
        code = code_raw.replace(".", "").replace(" ", "")
        if not code:
            continue

        desc = str(entry.get("description", "")).strip()
        tax = str(entry.get("tax_rate", "")).strip()
        unit = str(entry.get("unit", "")).strip()

        level = "GTIP"
        parent_code = None

        code_len = len(code)
        if code_len == 2:
            level = "CHAPTER"
        elif code_len == 4:
            level = "HEADING"
            parent_code = code[:2]
        elif code_len == 6:
            level = "SUBHEADING"
            parent_code = code[:4]
        else:
            level = "GTIP"
            parent_code = code[:6]

        # In-memory set lookup for fast batch insertion
        if code not in existing_codes:
            obj = TgtcGtipModel(
                gtip_code=code,
                level=level,
                chapter_code=code[:2],
                parent_code=parent_code,
                description=desc,
                tax_rate=tax,
                unit=unit,
                is_active=True,
                gecerlilik_baslangic="2026-01-01",
            )
            session.add(obj)
            existing_codes.add(code)
            inserted_count += 1
            if inserted_count % 2000 == 0:
                session.commit()
                print(f"Inserted {inserted_count} GTIP rows...")

    session.commit()
    print(f"GTİP Tree inserted. Total: {inserted_count}")

def wipe_bad_btbs(session: Session):
    print("Wiping bad RG-PDF records...")
    try:
        from api.db.database import GumrukEmsalKararModel
        e = session.query(GumrukEmsalKararModel).filter(GumrukEmsalKararModel.referans_no.like('RG-PDF-%')).delete(synchronize_session=False)
        session.commit()
        print(f"Deleted {e} obsolete unified Emsal records.")
    except Exception as ex:
        session.rollback()
        print(f"Error wiping bad records: {ex}")

if __name__ == "__main__":
    print("Starting TGTC Database Population...")
    init_orm_tables()
    
    with Session(engine) as session:
        wipe_bad_btbs(session)
        extract_gir_rules(session)
        extract_chapter_notes(session)
        populate_gtip_tree(session)
        
    print("TGTC Database Population Completed Successfully!")
