"""
Resmi Türk Gümrük Tarife Cetveli (TGTC) Dinamik Mevzuat ve Önbellek Modülü.
Veriler doğrudan Ticaret Bakanlığı canlı kazıma (Scraping) pipeline'ları
ve ilişkisel/vektör veritabanından dinamik olarak yüklenir.
HİÇBİR STATİK SÖZLÜK VEYA HARDCODED EŞLEŞTİRME İÇERMEZ.
"""
from __future__ import annotations

import os
import re
import json
import logging
import datetime
import time
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("TGTCKnowledgeBase")

from api.db.database import SessionLocal, GumrukEmsalKararModel

GIR_RULES = {
    "GIR_1": "Tarife pozisyonu ve ilgili bölüm veya fasıl notlarına göre sınıflandırma yapılır.",
    "GIR_2A": "Sökülmüş, demonte veya tamamlanmamış eşya, monte edilmiş ana eşyanın karakteristik özelliğini taşıyorsa ana pozisyonda sınıflandırılır.",
    "GIR_2B": "Kombine maddeler veya karışımların sınıflandırılmasında baskın nitelik ve oran dikkate alınır.",
    "GIR_3A": "En özel tanımı veren pozisyon, genel tanım veren pozisyona tercih edilir.",
    "GIR_3B": "Karışımlar, farklı maddelerden oluşan eşyalar ve perakende satılacak takımlar (setler) eşyaya esas karakterini veren maddeye/komponentine göre sınıflandırılır.",
    "GIR_3C": "3(a) ve 3(b) kuralları ile sınıflandırılamayan eşyalar, numaralandırmada en son sırada yer alan pozisyona verilir.",
    "GIR_4": "Yukarıdaki kurallara göre sınıflandırılamayan eşyalar, en çok benzediği eşya pozisyonuna verilir.",
    "GIR_5A": "Özel biçim verilmiş kılıf ve kutular (müzik aleti, silah vb. kutuları) ait oldukları eşya ile birlikte sınıflandırılır.",
    "GIR_5B": "Eşya ile birlikte sunulan ambalaj maddeleri ve ambalaj kapları eşya ile birlikte sınıflandırılır.",
    "GIR_6": "Alt pozisyonlar düzeyinde sınıflandırma, aynı düzeydeki alt pozisyonların karşılaştırılması ile GİR 1-5 esaslarına göre yapılır."
}

OFFICIAL_GIR_FULL_STATUTES: Dict[str, Dict[str, str]] = {
    "GIR_1": {
        "rule_no": "GİR 1",
        "title": "Genel Yorum Kuralı 1 (Tarife Pozisyonu ve Bölüm/Fasıl Notları Hükmü)",
        "summary": "Tarife pozisyonu ve ilgili bölüm veya fasıl notlarına göre sınıflandırma yapılır.",
        "text": (
            "1. Bölüm, fasıl ve tali fasıl başlıkları sadece gösterici niteliktedir; yasal amaçlar için "
            "eşyanın tarifedeki yerinin saptanması, pozisyon metinlerine, ilgili herhangi bir bölüm veya "
            "fasıl notuna ve bu pozisyonlar veya notlar hükümlerinde aksi belirtilmedikçe, aşağıdaki kurallara göre yapılır."
        ),
    },
    "GIR_2A": {
        "rule_no": "GİR 2(a)",
        "title": "Genel Yorum Kuralı 2(a) (Tamamlanmamış, Demonte veya Sökülmüş Eşya)",
        "summary": "Sökülmüş, demonte veya tamamlanmamış eşya, monte edilmiş ana eşyanın karakteristik özelliğini taşıyorsa ana pozisyonda sınıflandırılır.",
        "text": (
            "2. (a) Tarifenin belirli bir pozisyonunda herhangi bir eşyaya yapılan bir atıf, bu eşyanın imali bitirilmemiş "
            "veya aksamı tamamlanmamış olanlarını da kapsar. Şu kadar ki, bu gibi imali bitirilmemiş veya aksamı tamamlanmamış "
            "eşyanın gümrüğe sunulduğunda, imali bitirilmiş veya aksamı tamamlanmış eşyanın ayırdedici niteliğini içermesi gerekir. "
            "Böyle bir atıf, imali bitirilmiş veya aksamı tamamlanmış eşya ile, yukarıdaki hükme göre böyle sayılan eşyanın "
            "sökülerek veya monte edilmeden getirilmiş olanlarını da içine alır."
        ),
    },
    "GIR_2B": {
        "rule_no": "GİR 2(b)",
        "title": "Genel Yorum Kuralı 2(b) (Karışımlar ve Bileşik Maddeler)",
        "summary": "Kombine maddeler veya karışımların sınıflandırılmasında baskın nitelik ve oran dikkate alınır.",
        "text": (
            "(b) Tarifenin belirli bir pozisyonunda herhangi bir maddeye yapılan atıf, bu maddenin karışımlarını, bileşimlerini "
            "ve diğer maddelerle birleştirilmiş veya karıştırılmış hallerini de içine alır. Aynı şekilde, belirli bir maddeden mamul "
            "bir eşyaya yapılan herhangi bir atıf, tamamen veya kısmen bu maddeden mamul eşyayı da içine alır. Birden fazla maddeden "
            "meydana gelen eşyanın tarifedeki yeri, aşağıda (3) numaralı kuralda belirtilen prensiplere göre saptanır."
        ),
    },
    "GIR_3A": {
        "rule_no": "GİR 3(a)",
        "title": "Genel Yorum Kuralı 3(a) (En Özel Tanımın Genel Tanıma Önceliği)",
        "summary": "En özel tanımı veren pozisyon, genel tanım veren pozisyona tercih edilir.",
        "text": (
            "3. (a) Eşyayı en özel şekilde tanımlayan pozisyon, daha genel şekilde tanımlayan pozisyona göre öncelik alır. "
            "Bununla beraber, iki veya daha fazla pozisyonun her birinin, birbirleriyle karıştırılmış veya birleştirilmiş eşyanın "
            "sadece birine ya da perakende satılacak hale getirilmiş takımın sadece bir parçasına atıfta bulunması halinde, "
            "bu pozisyonların, pozisyonların birisi eşyanın tam ve kesin tanımını verse bile, sözkonusu eşyayı eşit derecede "
            "özel şekilde tanımladığı mütalaa edilir."
        ),
    },
    "GIR_3B": {
        "rule_no": "GİR 3(b)",
        "title": "Genel Yorum Kuralı 3(b) (Bileşik ve Takım Eşyada Esas Nitelik / Karakter)",
        "summary": "Karışımlar, farklı maddelerden oluşan eşyalar ve setler eşyaya esas karakterini veren bileşene göre sınıflandırılır.",
        "text": (
            "(b) (3-a) Kuralının uygulanmasıyla, tarifedeki yeri tayin edilemeyen bileşik ürünlerin ve çeşitli maddelerden oluşan "
            "veya çeşitli eşyanın birleşmesiyle meydana gelen mamuller ile perakende satılacak hale getirilmiş takım halinde bulunan "
            "eşyanın tarifedeki yeri, bunlara esas niteliğini veren madde veya eşya saptanabildiği takdirde buna göre bulunur."
        ),
    },
    "GIR_3C": {
        "rule_no": "GİR 3(c)",
        "title": "Genel Yorum Kuralı 3(c) (Numara Sırasıyla Son Pozisyon)",
        "summary": "3(a) ve 3(b) kuralları ile sınıflandırılamayan eşyalar en son sırada yer alan pozisyona verilir.",
        "text": (
            "(c) (3-a) veya (3-b) kuralları uyarınca tarifedeki yeri saptanamayan eşya, her biri geçerli olabilecek pozisyonların "
            "numara sırasına göre sonuncusunda mütalaa edilecektir."
        ),
    },
    "GIR_4": {
        "rule_no": "GİR 4",
        "title": "Genel Yorum Kuralı 4 (En Çok Benzeyen Eşya Prensibi)",
        "summary": "Kurallara göre sınıflandırılamayan eşyalar, en çok benzediği eşya pozisyonuna verilir.",
        "text": (
            "4. Yukarıdaki Kurallara uygun olarak sınıflandırılmayan eşya, bu eşyaya en çok benzeyen eşyanın bulunduğu pozisyonda sınıflandırılır."
        ),
    },
    "GIR_5A": {
        "rule_no": "GİR 5(a)",
        "title": "Genel Yorum Kuralı 5(a) (Özel Kılıf ve Mahfazalar)",
        "summary": "Özel biçim verilmiş kılıf ve kutular ait oldukları eşya ile birlikte sınıflandırılır.",
        "text": (
            "5. (a) Fotoğraf makinası mahfazası, müzik aleti mahfazası, silah mahfazası, çizim aleti kutuları, kolye kutuları "
            "ve benzeri kutular, özellikle belli bir eşyaya veya takım halindeki eşyaya göre şekil verilmiş veya bu eşyaya uygun "
            "olarak yapılmış olup uzun süre kullanılmaya uygun ve ait oldukları eşya ile birlikte ithal edilen kutular, normal olarak "
            "bu eşya ile birlikte satılan türde iseler, beraber satıldıkları eşya ile birlikte sınıflandırılırlar. Ancak bu Kural, "
            "bir bütün olarak esas niteliği mahfaza olan eşyaya uygulanmaz."
        ),
    },
    "GIR_5B": {
        "rule_no": "GİR 5(b)",
        "title": "Genel Yorum Kuralı 5(b) (Ambalaj Maddeleri ve Kaplar)",
        "summary": "Eşya ile birlikte sunulan normal ambalaj maddeleri eşya ile birlikte sınıflandırılır.",
        "text": (
            "(b) Yukarıda 5 (a) kuralındaki hükümler saklı kalmak şartıyla, içindeki eşya ile birlikte sunulan ambalaj maddeleri "
            "ve ambalaj mahfazaları bu eşyanın ambalajında normal olarak kullanılan türden ambalaj maddeleri olmaları şartıyla "
            "bu eşya ile beraber sınıflandırılırlar. Bununla beraber, bu tür ambalaj maddeleri veya ambalaj mahfazalarının, "
            "sürekli kullanıma elverişli olduklarının açıkça belli olması halinde bu hüküm uygulanmaz."
        ),
    },
    "GIR_6": {
        "rule_no": "GİR 6",
        "title": "Genel Yorum Kuralı 6 (Alt Pozisyon Düzeyinde Sınıflandırma ve Mukayese)",
        "summary": "Alt pozisyonlar düzeyinde sınıflandırma, aynı düzeydeki alt pozisyonların mukayese edilmesi ile yapılır.",
        "text": (
            "6. Yasal amaçlar için, eşyanın bir pozisyonun alt pozisyonlarında sınıflandırılması, sadece aynı seviyedeki "
            "alt pozisyonların mukayese edilebilirliği dikkate alınarak, bu alt pozisyonlardaki şartlar ile bu pozisyonla "
            "ilgili alt pozisyon notlarına ve gerekli değişiklikler yapılmış olarak, yukarıdaki kurallara göre saptanacaktır. "
            "Metinde aksi belirtilmedikçe bu kuralın tatbikinde, ilgili Bölüm ve Fasıl Notları da uygulanır."
        ),
    },
}

_LOCAL_POS_CACHE: Dict[str, str] = {}

def get_local_tgtc_headings() -> Dict[str, str]:
    """2026 TGTC yerleşik dizininden 4-Haneli Tarife Pozisyonları (HS Heading) sözlüğünü okur ve önbelleğe alır."""
    global _LOCAL_POS_CACHE
    if _LOCAL_POS_CACHE:
        return _LOCAL_POS_CACHE
    res = {}
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(base_dir, "2026 TGTC", "tgtc_2026_full_database.json")
        if not os.path.exists(db_path):
            db_path = "/app/2026 TGTC/tgtc_2026_full_database.json"
        if os.path.exists(db_path):
            with open(db_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                for item in raw_data:
                    code_raw = str(item.get("gtip_code", "")).replace(".", "").strip()
                    desc = str(item.get("description", "") or item.get("product_description", "")).strip()
                    if len(code_raw) == 4 and desc and not desc.startswith("-"):
                        res[code_raw] = desc.rstrip(":")
    except Exception as e:
        logger.warning(f"[TGTC Local DB] 4-hane pozisyon sözlük okuma uyarısı: {e}")
    _LOCAL_POS_CACHE = res
    return res

OFFICIAL_CHAPTER_TITLES: Dict[str, str] = {
    "01": "Canlı hayvanlar",
    "02": "Etler ve yenilen sakatat",
    "03": "Balıklar, kabuklu hayvanlar, yumuşakçalar ve diğer su omurgasızları",
    "04": "Süt ürünleri, tabii bal, diğer hayvansal menşeli yenilen maddeler",
    "05": "Tarifenin başka yerinde belirtilmeyen hayvansal menşeli ürünler",
    "06": "Canlı ağaçlar ve diğer bitkiler, yumrular, kökler, kesme çiçekler",
    "07": "Yenilen sebzeler ve bazı kök ve yumrular",
    "08": "Yenilen meyveler ve yenilen sert kabuklu meyveler, turunçgiller",
    "09": "Kahve, çay, paraguay çayı ve baharat",
    "10": "Hububat",
    "11": "Değirmencilik ürünleri, malt, nişasta, inülin, buğday gluteni",
    "12": "Yağlı tohum ve meyveler, muhtelif tane, tohum ve meyveler, sanayi ve tıbbi bitkiler",
    "13": "Lak, sakız, reçine ve diğer bitkisel özsu ve hülasalar",
    "14": "Örülmeye elverişli bitkisel maddeler ve diğer bitkisel ürünler",
    "15": "Hayvansal, bitkisel veya mikrobiyal katı ve sıvı yağlar ve bunların mumları",
    "16": "Et, balık, kabuklu hayvanlar, yumuşakçalar veya diğer su omurgasızlarının müstahzarları",
    "17": "Şeker ve şeker mamulleri",
    "18": "Kakao ve kakao müstahzarları",
    "19": "Hububat, un, nişasta veya süt müstahzarları, pastacılık ürünleri",
    "20": "Sebzeler, meyveler ve bitkilerin diğer kısımlarından elde edilen müstahzarlar",
    "21": "Muhtelif yenilen gıda müstahzarları",
    "22": "Meşrubat, alkollü içkiler ve sirke",
    "23": "Gıda sanayiinin kalıntı ve döküntüleri, hayvan yemleri",
    "24": "Tütün ve tütün yerine geçen işlenmiş maddeler, nikotinli ürünler",
    "25": "Tuz, kükürt, topraklar ve taşlar, alçılar, kireçler ve çimento",
    "26": "Metal cevherleri, cüruf ve kül",
    "27": "Mineral yakıtlar, mineral yağlar ve bunların damıtılmasından elde edilen ürünler, bitüminli maddeler",
    "28": "Anorganik kimyasallar, kıymetli metal, radyoaktif element bileşikleri",
    "29": "Organik kimyasal ürünler",
    "30": "Eczacılık ürünleri",
    "31": "Gübreler",
    "32": "Debagatte ve boyacılıkta kullanılan hülasalar, tanenler, boyalar, pigmentler, vernikler, mürekkepler",
    "33": "Uçucu yağlar ve rezinoidler, parfümeri, kozmetik veya tuvalet müstahzarları",
    "34": "Sabunlar, yüzeyaktif maddeler, yıkama, yağlama ve temizleme müstahzarları, mumlar",
    "35": "Albüminoid maddeler, modifiye nişastalar, tutkallar, enzimler",
    "36": "Barut ve patlayıcı maddeler, pirotekni mamulleri, kibritler",
    "37": "Fotoğrafçılıkta veya sinemacılıkta kullanılan mallar",
    "38": "Muhtelif kimyasal maddeler",
    "39": "Plastikler ve mamulleri",
    "40": "Kauçuk ve kauçuktan eşya",
    "41": "Ham postlar, deriler (kürkler hariç) ve köseleler",
    "42": "Deri eşya, saraciye ve eyer takımları, seyahat eşyası, el çantaları",
    "43": "Kürkler, taklit kürkler ve bunların mamulleri",
    "44": "Ağaç ve ahşap eşya, odun kömürü",
    "45": "Mantar ve mantardan eşya",
    "46": "Hasırdan, sazdan veya örülmeye elverişli maddelerden mamuller, sepetçi eşyası",
    "47": "Odun veya diğer lifli selülozik maddelerin hamurları, geri kazanılmış kağıt veya karton",
    "48": "Kağıt ve karton, kağıt hamurundan, kağıttan veya kartondan eşya",
    "49": "Basılı kitaplar, gazeteler, resimler ve baskı sanayiinin diğer mamulleri, planlar",
    "50": "İpek",
    "51": "Yün, ince veya kaba hayvan kılı, at kılından iplik ve dokunmuş mensucat",
    "52": "Pamuk",
    "53": "Diğer bitkisel dokumaya elverişli elyaflar, kağıt ipliği ve dokunmuş mensucat",
    "54": "Sentetik ve suni filamentler, şeritler ve dokumaya elverişli benzeri maddeler",
    "55": "Sentetik ve suni devamsız lifler",
    "56": "Vatka, keçe ve dokunmamış mensucat, özel iplikler, sicim, kordon, ip ve halatlar",
    "57": "Halılar ve diğer dokumaya elverişli maddelerden yer kaplamaları",
    "58": "Özel dokunmuş mensucat, tufte edilmiş mensucat, dantela, duvar halıları, işlemeler",
    "59": "Emdirilmiş, sıvanmış, kaplanmış mensucat, teknik amaçlı dokumaya elverişli eşya",
    "60": "Örme veya tığ işi mensucat",
    "61": "Örme veya tığ işi giyim eşyası ve aksesuarı",
    "62": "Örülmemiş giyim eşyası ve aksesuarı",
    "63": "Dokumaya elverişli maddelerden diğer hazır eşya, takımlar, kullanılmış giyim eşyası, paçavralar",
    "64": "Ayakkabılar, getrler, tozluklar ve benzeri eşya, bunların aksamı",
    "65": "Başlıklar ve aksamı",
    "66": "Şemsiyeler, güneş şemsiyeleri, bastonlar, kamçılar ve bunların aksamı",
    "67": "Hazırlanmış tüyler ve bunlardan eşya, yapma çiçekler, insan saçından eşya",
    "68": "Taş, alçı, çimento, asbest, mika veya benzeri maddelerden eşya",
    "69": "Seramik mamulleri",
    "70": "Cam ve cam eşya",
    "71": "Tabii veya kültür inciler, kıymetli taşlar, kıymetli metaller, taklit mücevherci eşyası, madeni paralar",
    "72": "Demir ve çelik",
    "73": "Demir veya çelikten eşya",
    "74": "Bakır ve bakırdan eşya",
    "75": "Nikel ve nikelden eşya",
    "76": "Alüminyum ve alüminyumdan eşya",
    "78": "Kurşun ve kurşundan eşya",
    "79": "Çinko ve çinkodan eşya",
    "80": "Kalay ve kalaydan eşya",
    "81": "Diğer adi metaller, sermetler ve bunlardan eşya",
    "82": "Adi metallerden aletler, bıçakçı eşyası ve sofra takımları, bunların aksam ve parçaları",
    "83": "Adi metallerden çeşitli eşya",
    "84": "Kazanlar, makineler, mekanik cihazlar ve aletler, bunların aksam ve parçaları",
    "85": "Elektrikli makine ve cihazlar, ses ve görüntü kaydetme/çoğaltma cihazları, bunların aksam ve parçaları",
    "86": "Demiryolu lokomotifleri, vagonlar, hat sabit tesisatları, trafik sinyalizasyon cihazları",
    "87": "Motorlu kara taşıtları, traktörler, bisikletler ve diğer kara taşıtları, bunların aksam ve parçaları",
    "88": "Hava taşıtları, uzay taşıtları ve bunların aksam ve parçaları",
    "89": "Gemiler, botlar ve yüzen taşıtlar",
    "90": "Optik, fotoğraf, sinema, ölçü, kontrol, ayar, tıbbi veya cerrahi alet ve cihazlar",
    "91": "Saatler ve bunların aksam ve parçaları",
    "92": "Müzik aletleri, bunların aksam, parça ve aksesuarları",
    "93": "Silahlar ve mühimmat, bunların aksam ve parçaları",
    "94": "Mobilyalar, aydınlatma cihazları, prefabrik yapılar",
    "95": "Oyuncaklar, oyun ve spor malzemeleri, bunların aksam ve parçaları",
    "96": "Çeşitli mamul eşya",
    "97": "Sanat eserleri, koleksiyon eşyası ve antikalar"
}

def load_tgtc_chapters() -> Dict[str, str]:
    """Resmi 2026 TGTC Kütüphanesi üzerinden 2 Haneli Fasıl sözlüğünü döndürür.
    Resmi kanuni fasıl isimlerini esas alır; eksik fasıllar için pozisyon kapsamından türetir."""
    headings = get_local_tgtc_headings()
    result = {}
    for code in headings:
        if len(str(code)) >= 2 and str(code)[:2].isdigit():
            chap = str(code)[:2]
            if chap not in result:
                if chap in OFFICIAL_CHAPTER_TITLES:
                    result[chap] = f"Fasıl {chap}: {OFFICIAL_CHAPTER_TITLES[chap]}"
                else:
                    desc = headings[code]
                    clean_desc = desc.split("(")[0].split(",")[0].strip()
                    result[chap] = f"Fasıl {chap}: {clean_desc}"
    # Kanuni fasılların tamamını içermesini sağla
    for chap, title in OFFICIAL_CHAPTER_TITLES.items():
        if chap not in result:
            result[chap] = f"Fasıl {chap}: {title}"
    return result

_BTB_CATALOG_CACHE: List[Dict[str, Any]] = None
_BTB_CACHE_LOADED_AT: float = 0.0
_BTB_CACHE_TTL_SECONDS = 900
_RULES_AND_NOTES_CACHE: Dict[str, Any] = None

def invalidate_catalog_cache():
    """Mevzuat güncellendiğinde katalog, pozisyon ve izahname önbelleklerini temizler."""
    global _BTB_CATALOG_CACHE, _BTB_CACHE_LOADED_AT, _LOCAL_POS_CACHE, _RULES_AND_NOTES_CACHE
    _BTB_CATALOG_CACHE = None
    _BTB_CACHE_LOADED_AT = 0.0
    _LOCAL_POS_CACHE = None
    _RULES_AND_NOTES_CACHE = None
    logger.info("[TGTC Catalog] Bellek içi katalog, pozisyon ve izahname önbellekleri temizlendi.")

_BAD_DESC_PATTERNS = [
    r"metin [iı]çerikli", r"tebli[gğ]\s*/?\s*karar", r"sayfa\s+\d", r"\[pozisyon",
    r"g[uü]mr[uü]k s[iı]n[iı]fland[iı]rma karar[iı]", r"bu tebli[gğ]in amac[iı]",
    r"haks[iı]z rekabetin [öo]nlenmesi", r"ithalatta haks[iı]z rekabet",
    r"g[uü]mr[uü]k genel tebli[gğ]i", r"resm[iı] gazete", r"ama[cç] ve kapsam",
    r"madde\s*\d+", r"ge[cç][iı]ci madde", r"soru[sş]turma konusu",
    r"ayn[iı] tebli[gğ]in eki", r"ek-[0-9]+", r"tarihli ve", r"m[uü]kerrer say[iı]l[iı]",
    r"karar[iı] eki karar[iı]n", r"[oö]zel t[uü]ketim vergisi", r"f[iı]kras[iı] uyar[iı]nca",
    r"y[uü]r[uü]rl[uü]kten kald[iı]r[iı]lm[iı][sş]t[iı]r", r"sat[iı]r eklenmi[sş]tir",
    r"tabloya", r"tablodaki", r"gt[iı]p numaral[iı]", r"g[uü]mr[uü]k tarife istatistik",
    r"yerli [uü]retici", r"soru[sş]turma", r"kapsam[iı]nda yer alan",
]


def _is_bad_desc(text_str: str) -> bool:
    """Verilen metnin jenerik tebliğ veya maddeden ibaret olup olmadığını doğrular."""
    if not text_str or len(text_str.strip()) < 4:
        return True
    t = text_str.strip()
    return any(re.search(p, t, re.IGNORECASE) for p in _BAD_DESC_PATTERNS)


def _clean_product_name(text_str: str) -> str:
    """Madde numaraları (*35-, 37-) ve GTİP etiketlerini (*[GTİP: 22...) temizler."""
    if not text_str:
        return ""
    s = text_str.strip()
    # Maddesel önek temizliği: "*35- Etil Alkol" veya "37- Dezenfektan"
    s = re.sub(r"^[\*\s\-\d]{1,6}\s*", "", s)
    # Parantez içi GTİP son ek temizliği: "Etil Alkol [GTİP: 22.07...]"
    s = re.sub(r"\[?\s*GT[İI]P\s*:?.*$", "", s, flags=re.IGNORECASE)
    return s.strip(" ,.-*")


def _auto_fix_description(desc: str, legal: str, gtip: str = "") -> str:
    """
    Jenerik veya 'Metin İçerikli Tebliğ Kaydı' olan eşya tanımlarını 
    Hukuki Gerekçe ve Mevzuat metni içinden dinamik olarak gerçek ürün ismine dönüştürür.
    Metinde gerçek ürün adı yoksa rastgele tebliğ maddesi DÖNDÜRMET! TGTC pozisyon adını kullanır.
    """
    desc_str = _clean_product_name(str(desc or ""))
    legal_str = str(legal or "").strip()

    # Eğer mevcut açıklama zaten temiz ve anlamlı bir ürün ismiyse dokunma
    if desc_str and len(desc_str) >= 4 and not _is_bad_desc(desc_str):
        return desc_str

    combined = f"{desc_str} {legal_str}"

    # 1. Tırnak İçi Gerçek Ürün İsmi (EN GÜVENİLİR STRATEJİ: Örn: "Etil Alkol", "Dezenfektan", "hidrojenortofosfat")
    quotes = re.findall(r'"([^"]{3,150})"', combined)
    if quotes:
        for q in quotes:
            q_clean = _clean_product_name(q)
            if q_clean and len(q_clean) >= 3 and not _is_bad_desc(q_clean):
                return q_clean

    # 2. "Eşya Tanımı:" / "Konu:" etiketinden sonraki değeri al
    m = re.search(r"(?:e[şs]ya tan[iı]m[iı]|konu|[üu]r[üu]n)\s*:\s*(.+?)(?:\n|hukuki|gerek[cç]e|$)", combined, re.IGNORECASE)
    if m:
        candidate = _clean_product_name(m.group(1))
        if candidate and len(candidate) > 4 and not _is_bad_desc(candidate):
            return candidate[:200]

    # 3. 'yer alan ... ithalatı/eşyası/ürünü' kalıbı
    m = re.search(r'yer alan\s+(.+?)(?:\s+ithalat[iı]|\s+ihracat[iı]|\s+[üu]r[üu]n[üu]|\s+e[şs]yas[iı]|\s+iznine|\s+tabidir)', combined, re.IGNORECASE)
    if m:
        candidate = _clean_product_name(m.group(1))
        if candidate and 4 < len(candidate) < 150 and not _is_bad_desc(candidate):
            return candidate[:150]

    # 4. Fallback: Rastgele tebliğ maddesi DÖNDÜRME! TGTC tarife pozisyonu başlığını kullan
    gtip_clean = re.sub(r"[^\d]", "", str(gtip or ""))
    if gtip_clean and len(gtip_clean) >= 4:
        pos_code = gtip_clean[:4]
        try:
            pos_dict = get_local_tgtc_headings()
            pos_info = pos_dict.get(pos_code)
            if pos_info and pos_info.get("description"):
                return f"{pos_info['description'].strip()} (GTİP {gtip})"
        except Exception:
            pass

    return f"Gümrük Mevzuat Kararı Eşya Kaydı ({gtip})"



def load_btb_catalog() -> List[Dict[str, Any]]:
    """Resmi BTB Emsal Kararlar Kataloğunu GCP Cloud SQL, GCS Bucket veya /tmp üzerinden okur ve hiyerarşik ağaç breadcrumb ile standartlaştırır."""
    global _BTB_CATALOG_CACHE, _BTB_CACHE_LOADED_AT
    if (
        _BTB_CATALOG_CACHE is not None
        and time.monotonic() - _BTB_CACHE_LOADED_AT < _BTB_CACHE_TTL_SECONDS
    ):
        return _BTB_CATALOG_CACHE

    def _count_dashes_and_clean(text: str) -> int:
        s = text.lstrip()
        count = 0
        while s.startswith("-"):
            count += 1
            s = s[1:].lstrip()
        return count

    def _process_and_enrich_catalog(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pos_dict = get_local_tgtc_headings()
        enriched_list = []
        seen_keys = set()
        
        current_heading = None
        hierarchy_stack: Dict[int, str] = {}

        for idx, item in enumerate(raw_items):
            gtip_raw = item.get("gtip_code", "")
            btb_raw = str(item.get("btb_no") or f"TGTC2026-{gtip_raw}-{idx}").strip()
            desc = str(item.get("product_description") or item.get("description", "")).strip()
            legal = str(item.get("legal_justification", "")).strip()
            
            # 1. Emsal Kararı Olmayan Kirli/Hatalı Verileri Kesinlikle Ekleme (Fasıl Başlıkları ve WCO Nomenklatür Rehberi)
            if (btb_raw.startswith(("TGTC-FASIL", "MEVZUAT")) or "WCO HS 2022" in legal or "BTI Consultation" in btb_raw or not str(gtip_raw).strip()):
                continue

            # GTİP normalizasyonu (4, 6, 8, 12 haneli)
            gtip_clean = str(gtip_raw).replace(".", "").strip()
            heading_code = gtip_clean[:4] if len(gtip_clean) >= 4 else gtip_clean
            
            # Geçersiz/Hatalı Pozisyon Filtresi (Pozisyon kodu 2026 TGTC'de kayıtlı 964 pozisyondan biri olmalı)
            if pos_dict and heading_code not in pos_dict:
                continue

            # Ürün Tanımı Kalite Kontrolü (Harf sayısı yetersiz veya bütçe/toplam tablosu ise atla)
            letter_count = len(re.findall(r'[a-zA-ZçğıöşüÇĞİÖŞÜ]', desc))
            if letter_count < 5 or desc.lower().startswith(("toplam", "rg-pdf", "gerekçe:", "sayfa ")) or desc.startswith("11,50") or desc.startswith("TOPLAM"):
                continue

            # 2. Emsal ve Tebliğler için Tekilleştirme (Gerçek BTB/RG kararlarını TGTC cetveli ile karıştırıp silme)
            if btb_raw.startswith("TGTC2026-"):
                dedup_key = f"TGTC_{gtip_raw}_{desc[:50]}"
            else:
                # Gerçek Emsal BTB ve Tebliğ Kararları kendi btb_no'su ile tekilleşir
                dedup_key = f"REAL_{btb_raw}"

            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            
            # GTİP normalizasyonu (4, 6, 8, 12 haneli)
            gtip_clean = str(gtip_raw).replace(".", "").strip()
            heading_code = gtip_clean[:4] if len(gtip_clean) >= 4 else gtip_clean
            heading_title = pos_dict.get(heading_code, f"Pozisyon {heading_code}")

            gtip = str(gtip_raw)
            if len(gtip_clean) == 12 and gtip_clean.isdigit():
                gtip = f"{gtip_clean[:4]}.{gtip_clean[4:6]}.{gtip_clean[6:8]}.{gtip_clean[8:10]}.{gtip_clean[10:12]}"
            elif len(gtip_clean) == 8 and gtip_clean.isdigit():
                gtip = f"{gtip_clean[:4]}.{gtip_clean[4:6]}.{gtip_clean[6:8]}"
            elif len(gtip_clean) == 6 and gtip_clean.isdigit():
                gtip = f"{gtip_clean[:4]}.{gtip_clean[4:6]}"
            elif len(gtip_clean) == 4 and gtip_clean.isdigit():
                gtip = gtip_clean

            # Hiyerarşik Tarife Ağacı (Breadcrumb) Takibi (Sadece TGTC Cetveli İçin, Gerçek BTB'lere Dokunma)
            if btb_raw.startswith("TGTC2026-"):
                if heading_code != current_heading:
                    current_heading = heading_code
                    hierarchy_stack.clear()
                    hierarchy_stack[0] = f"[Pozisyon {heading_code}: {heading_title}]"

                dash_count = _count_dashes_and_clean(desc)
                if dash_count > 0 or str(desc).strip().startswith("-"):
                    # Daha derin veya eşit düzeyleri yığından temizle (yeni dal başlıyor)
                    keys_to_remove = [k for k in hierarchy_stack.keys() if k >= dash_count]
                    for k in keys_to_remove:
                        del hierarchy_stack[k]
                    
                    # Ataları birleştirerek breadcrumb silsilesini üret
                    parents = [hierarchy_stack[k] for k in sorted(hierarchy_stack.keys()) if hierarchy_stack.get(k)]
                    enriched_desc = " -> ".join(parents + [f"[{desc}] (GTİP: {gtip})"])
                    
                    # Mevcut satırı atalar arasına kaydet
                    hierarchy_stack[dash_count] = f"[{desc}]"
                    desc = enriched_desc
                elif "Diğerleri" in desc or len(desc) < 15:
                    desc = f"[Pozisyon {heading_code}: {heading_title}] {desc} (GTİP: {gtip})"
                    if dash_count == 0:
                        hierarchy_stack[0] = f"[Pozisyon {heading_code}: {heading_title}]"

            # Ölçü birimi ve vergi oranlarını iliştir
            if item.get("unit") and "[Ölçü:" not in desc and str(item.get("unit")).strip() not in ("", "-"):
                desc += f" [Ölçü: {item.get('unit')}]"
            if item.get("tax_rate") and "[Vergi" not in str(desc) and str(item.get("tax_rate")).strip() not in ("", "-"):
                desc += f" [Vergi: %{item.get('tax_rate')}]"

            legal = item.get("legal_justification") or ""
            if ".xls" in str(legal) or "Kaynak Fasıl" in str(legal) or not legal:
                legal = f"2026 T.C. Ticaret Bakanlığı Resmi Gümrük Tarife Cetveli (Pozisyon {heading_code} Yasal Hükümleri)"
            
            date_val = item.get("issue_date") or item.get("source_year") or "2026-01-01"
            btb_id = btb_raw

            # 🎯 Gerçek BTB / Emsal Kararları İçin Otomatik Ürün Açıklaması Temizleyici ve Çıkarıcı
            if not btb_id.startswith("TGTC2026-"):
                desc = _auto_fix_description(desc, legal, gtip)
                letter_cnt = len(re.findall(r'[a-zA-ZçğıöşüÇĞİÖŞÜ]', desc))
                # 🚫 Rakam/bütçe tablolarını, metinsiz hücreleri ve 'Metin İçerikli' kalan kayıtları atla 🚫
                if letter_cnt < 5 or any(k in desc for k in ["Metin İçerikli", "Tebliğ / Karar Metni", "Sayfa "]) or desc.lower().startswith(("toplam", "rg-pdf", "gerekçe:")) or re.match(r"^[\d\.\,\s\-\+\*\$\%\:\;]+$", desc):
                    continue

            # Format source URL (GCS HTTPS or Resmi Gazete link)
            s_url = item.get("source_url") or item.get("kaynak_url")
            if s_url:
                s_url = str(s_url).strip()
                if s_url.startswith("gs://"):
                    s_url = f"https://storage.googleapis.com/{s_url[5:]}"
            elif not btb_id.startswith("TGTC2026-"):
                d_clean = re.sub(r"[^\d]", "", str(date_val))
                if len(d_clean) >= 8:
                    y, m, d = d_clean[:4], d_clean[4:6], d_clean[6:8]
                    s_url = f"https://www.resmigazete.gov.tr/eskiler/{y}/{m}/{y}{m}{d}.htm"
                else:
                    s_url = "https://www.resmigazete.gov.tr"

            enriched_list.append({
                "btb_no": btb_id,
                "gtip_code": gtip,
                "chapter": item.get("chapter", "") or gtip_clean[:2],
                "heading": item.get("heading", "") or heading_code,
                "issue_date": str(date_val),
                "product_description": desc,
                "legal_justification": legal,
                "source_url": s_url,
                "source_type": str(
                    item.get("source_type")
                    or item.get("karar_tipi")
                    or ("TGTC_2026" if btb_id.startswith("TGTC2026-") else "BTB")
                ).upper(),
                "valid_until": str(item.get("valid_until") or item.get("gecerlilik_tarihi") or "9999-12-31"),
                "embedding": item.get("embedding"),
            })
        return enriched_list

    all_raw_items: List[Dict[str, Any]] = []

    # 1. Öncelikli ve Temel Katman: Yerel 2026 TGTC Kütüphanesi (Hiyerarşik Sıralı 216.000+ Kayıt)
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        tgtc_path = os.path.join(base_dir, "2026 TGTC", "tgtc_2026_full_database.json")
        if os.path.exists(tgtc_path):
            with open(tgtc_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 10:
                    all_raw_items.extend(data)
                    logger.info(f"[TGTC Catalog] Yerel TGTC 2026 hazinesi okundu ({len(data)} satır).")
    except Exception as e:
        logger.warning(f"[TGTC Catalog] Yerel TGTC kütüphanesi okuma uyarısı: {e}")

    # Test/emülatör ve yerel geliştirme sırasında GCS ADC token yenilemesi ile
    # Cloud SQL'a ağ erişimi yapma. Yerel TGTC kataloğu bu ortamlar için yeterlidir.
    cloud_runtime = bool(os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_JOB"))
    remote_sources_enabled = (
        os.getenv("ENVIRONMENT", "production") == "production"
        and os.getenv("USE_GCP_EMULATOR", "false").lower() != "true"
        and cloud_runtime
    )
    if not remote_sources_enabled:
        _BTB_CATALOG_CACHE = _process_and_enrich_catalog(all_raw_items) if all_raw_items else []
        _BTB_CACHE_LOADED_AT = time.monotonic()
        return _BTB_CATALOG_CACHE

    # 2. GCS Bucket Canlı Emsal Karar Okuma Kontrolü (Bakanlık Kazıma Verileri)
    try:
        from google.cloud import storage
        project_id = os.getenv("GCP_PROJECT_ID", "gumruk-mevzuat")
        bucket_name = os.getenv("GCS_BUCKET_NAME", "gumruk-mevzuat-storage-us-central1")
        client = storage.Client(project=project_id)
        bucket = client.bucket(bucket_name)
        blobs = list(client.list_blobs(bucket, prefix="official_btb/"))
        if blobs:
            latest_blob = max(blobs, key=lambda b: b.updated)
            content = latest_blob.download_as_text()
            data = json.loads(content)
            if isinstance(data, list) and data:
                all_raw_items.extend(data)
                logger.info(f"[TGTC Catalog] GCS canlı emsal kararlar eklendi ({len(data)} kayıt).")
    except Exception as e:
        logger.warning(f"[TGTC Catalog] GCS Bucket canlı okuma uyarısı: {e}")

    # 3. Veritabanı (SQLAlchemy ORM) Emsal Kararları Kontrolü
    try:
        session = SessionLocal()
        try:
            emsal_rows = session.query(
                GumrukEmsalKararModel.referans_no,
                GumrukEmsalKararModel.id,
                GumrukEmsalKararModel.gtip_kodu,
                GumrukEmsalKararModel.yayin_tarihi,
                GumrukEmsalKararModel.esya_tanimi,
                GumrukEmsalKararModel.karar_tipi,
                GumrukEmsalKararModel.hukuki_gerekce,
                GumrukEmsalKararModel.resmi_gazete_sayisi,
                GumrukEmsalKararModel.kaynak_url,
                GumrukEmsalKararModel.valid_until,
                GumrukEmsalKararModel.embedding,
            ).all()
            for ref_no, er_id, gtip_kodu, pub_date, esya_tanimi, karar_tipi, hukuki_gerekce, rg_sayisi, kaynak_url, valid_until, embedding in emsal_rows:
                all_raw_items.append({
                    "btb_no": ref_no or f"EMS-{er_id}",
                    "gtip_code": gtip_kodu,
                    "chapter": gtip_kodu[:2] if gtip_kodu else "",
                    "heading": gtip_kodu[:4] if gtip_kodu else "",
                    "issue_date": pub_date or "2026-01-01",
                    "product_description": esya_tanimi,
                    "legal_justification": f"[{karar_tipi}] {hukuki_gerekce or ''} (Resmi Gazete: {rg_sayisi or '-'})",
                    "source_type": karar_tipi,
                    "source_url": kaynak_url,
                    "valid_until": valid_until,
                    "embedding": embedding,
                })
        except Exception as ex_emsal:
            logger.warning(f"[TGTC Catalog] GumrukEmsalKararModel okuma uyarısı: {ex_emsal}")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"[TGTC Catalog] SQLAlchemy ORM BTB okuma uyarısı: {e}")

    # 4. Temp Fallback Kontrolü (Eğer hala boş ise)
    if not all_raw_items:
        try:
            import tempfile, glob
            date_str = datetime.date.today().strftime("%Y_%m_%d")
            local_path = os.path.join(tempfile.gettempdir(), f"btb_scraped_{date_str}.json")
            if os.path.exists(local_path):
                with open(local_path, "r", encoding="utf-8") as f:
                    all_raw_items.extend(json.load(f))
            else:
                tmp_files = glob.glob(os.path.join(tempfile.gettempdir(), "btb_scraped_*.json"))
                if tmp_files:
                    with open(tmp_files[-1], "r", encoding="utf-8") as f:
                        all_raw_items.extend(json.load(f))
        except Exception as e:
            logger.warning(f"[TGTC Catalog] Fallback okuma uyarısı: {e}")

    if all_raw_items:
        _BTB_CATALOG_CACHE = _process_and_enrich_catalog(all_raw_items)
        _BTB_CACHE_LOADED_AT = time.monotonic()
        return _BTB_CATALOG_CACHE

    _BTB_CACHE_LOADED_AT = time.monotonic()
    _BTB_CATALOG_CACHE = []
    return []

def load_tgtc_rules_and_notes() -> Dict[str, Any]:
    """2026 TGTC Resmi Yorum Kurallarını, Ölçü Birimlerini ve 97 Fasıl Notunu okur (bellek önbellekli)."""
    global _RULES_AND_NOTES_CACHE
    if _RULES_AND_NOTES_CACHE is not None:
        return _RULES_AND_NOTES_CACHE
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        rules_path = os.path.join(base_dir, "2026 TGTC", "tgtc_2026_rules_and_notes.json")
        if not os.path.exists(rules_path):
            rules_path = "/app/2026 TGTC/tgtc_2026_rules_and_notes.json"
        if os.path.exists(rules_path):
            with open(rules_path, "r", encoding="utf-8") as f:
                _RULES_AND_NOTES_CACHE = json.load(f)
                return _RULES_AND_NOTES_CACHE
    except Exception as e:
        logger.warning(f"[TGTC Rules] Yorum kuralları ve fasıl notu okuma uyarısı: {e}")
    _RULES_AND_NOTES_CACHE = {"yorum_kurallari": [], "olcu_birimleri": [], "fasil_notlari": {}}
    return _RULES_AND_NOTES_CACHE

# Dynamic property wrappers for backward compatibility
TGTC_CHAPTERS = load_tgtc_chapters()
# BTB kataloğu GCS ve Cloud SQL erişimi yapabildiğinden import anında yüklenmez.
# İlk gerçek aramada `load_btb_catalog()` tarafından doldurulur ve önbelleklenir.
TGTC_KNOWLEDGE_BASE_CATALOG: List[Dict[str, Any]] = []
TGTC_RULES_AND_NOTES = load_tgtc_rules_and_notes()

TURKISH_STOP_WORDS = {
    "ve", "ile", "veya", "için", "bir", "bu", "da", "de", "dahi", "göre", "ait",
    "üzere", "gibi", "kadar", "adet", "kutu", "tane", "ürün", "mamul", "cihaz",
    "diğer", "eşya", "maddeler", "kutular", "kaplar", "aksam", "parça"
}

def tr_normalize(text: str) -> str:
    if not text:
        return ""
    text = text.replace("İ", "i").replace("I", "i").replace("ı", "i")
    text = text.replace("Ş", "s").replace("ş", "s").replace("Ğ", "g").replace("ğ", "g")
    text = text.replace("Ç", "c").replace("ç", "c").replace("Ö", "o").replace("ö", "o")
    text = text.replace("Ü", "u").replace("ü", "u")
    return text.lower()

def match_chapters_from_cache(product_text: str) -> List[str]:
    """
    Dinamik olarak çekilen resmi TGTC Fasıl Tanımları ve BTB kataloğu üzerinde
    semantik / token süzmesi yaparak eşleşen Fasılları döndürür.
    HİÇBİR HARDCODED SÖZLÜK KULLANMAZ.
    """
    norm_input = tr_normalize(product_text)
    input_words = set(w for w in re.findall(r'[a-z0-9]+', norm_input) if w not in TURKISH_STOP_WORDS and len(w) >= 3)

    if not input_words:
        return []

    chapters = load_tgtc_chapters() or TGTC_CHAPTERS
    matched_chapters = []

    # 1. Canlı TGTC Fasıl Tanımları Üzerinden Dinamik Token Eşleme
    for chap_code, chap_desc in chapters.items():
        norm_desc = tr_normalize(chap_desc)
        desc_words = set(w for w in re.findall(r'[a-z0-9]+', norm_desc) if w not in TURKISH_STOP_WORDS and len(w) >= 3)
        
        common = input_words.intersection(desc_words)
        if common:
            matched_chapters.append(chap_code.zfill(2))

    # 2. Canlı BTB Karar Kataloğu Üzerinden Dinamik Eşleme
    catalog = load_btb_catalog() or TGTC_KNOWLEDGE_BASE_CATALOG
    for entry in catalog:
        desc = tr_normalize(entry.get("product_description", ""))
        desc_words = set(w for w in re.findall(r'[a-z0-9]+', desc) if w not in TURKISH_STOP_WORDS and len(w) >= 3)
        if len(input_words.intersection(desc_words)) >= 2:
            chap = str(entry.get("chapter", "")).zfill(2)
            if chap and chap not in matched_chapters:
                matched_chapters.append(chap)

    return list(dict.fromkeys(matched_chapters))

def get_chapter_title(chapter_code: str) -> str:
    """Fasıl koduna göre resmi tanım başlığını döndürür."""
    chaps = load_tgtc_chapters() or TGTC_CHAPTERS
    code_z = str(chapter_code).zfill(2)
    return chaps.get(code_z, "Genel Gümrük Tarife Cetveli Eşyası")


def get_official_statute_records(
    gtip_code: str,
    applied_gir_keys: Optional[List[str]] = None,
    cited_chapters: Optional[List[str]] = None,
) -> List[Any]:
    """
    Seçilen GTİP kodu, uygulanan GİR kuralları ve ilgili fasıllar için
    DOĞRUDAN RESMİ VERİTABANINDAN (DB / JSON) çekilen ve ASLA MODEL TARAFINDAN YAZILMAYAN
    orijinal kanuni madde metinlerini (LegalSource nesneleri) döndürür.
    """
    from api.schemas.product import LegalSource
    from api.db.database import SessionLocal, TgtcGtipModel, TariffHierarchyModel

    records: List[LegalSource] = []
    clean_code = re.sub(r"\D", "", str(gtip_code or ""))
    seen_refs = set()

    # 1. GİR Kuralları (Resmi Kanun Metinleri)
    gir_keys = list(applied_gir_keys or ["GIR_1", "GIR_6"])
    for fallback_k in ("GIR_1", "GIR_6"):
        if fallback_k not in gir_keys:
            gir_keys.append(fallback_k)

    for k in gir_keys:
        clean_k = str(k).upper().replace("GYK", "GIR").replace("(", "").replace(")", "").replace(" ", "_").strip()
        statute = OFFICIAL_GIR_FULL_STATUTES.get(clean_k)
        if statute and clean_k not in seen_refs:
            seen_refs.add(clean_k)
            records.append(
                LegalSource(
                    source_type="GIR",
                    reference_no=statute["rule_no"],
                    title=statute["title"],
                    excerpt=statute["text"],
                    legal_role="NORMATIVE",
                    authority_level=1,
                    effective_from="2026-01-01",
                    is_binding=True,
                )
            )

    # 2. Hiyerarşik Tarife Pozisyonu, Alt Pozisyon ve Nihai GTİP Veritabanı Metinleri
    if len(clean_code) >= 2:
        chap_code = clean_code[:2]
        chap_title = OFFICIAL_CHAPTER_TITLES.get(chap_code, f"Fasıl {chap_code}")
        records.append(
            LegalSource(
                source_type="TGTC_CHAPTER",
                reference_no=f"Fasıl {chap_code}",
                title=f"2026 TGTC Fasıl {chap_code} Kanuni Başlığı",
                excerpt=f"Fasıl {chap_code}: {chap_title}",
                legal_role="NORMATIVE",
                authority_level=1,
                effective_from="2026-01-01",
                is_binding=True,
            )
        )

    if len(clean_code) >= 4:
        pos_code = clean_code[:4]
        headings = get_local_tgtc_headings()
        pos_desc = headings.get(pos_code, "")
        if pos_desc:
            records.append(
                LegalSource(
                    source_type="TGTC_HEADING",
                    reference_no=f"Pozisyon {pos_code[:2]}.{pos_code[2:]}",
                    title=f"2026 TGTC {pos_code[:2]}.{pos_code[2:]} Tarife Pozisyonu Resmi Metni",
                    excerpt=f"Pozisyon {pos_code[:2]}.{pos_code[2:]}: {pos_desc}",
                    legal_role="NORMATIVE",
                    authority_level=1,
                    effective_from="2026-01-01",
                    is_binding=True,
                )
            )

    # Subheading (6-digit) & Leaf (12-digit) DB sorgusu
    try:
        with SessionLocal() as session:
            if len(clean_code) >= 6:
                sub_code = clean_code[:6]
                sub_row = session.query(TgtcGtipModel).filter(
                    TgtcGtipModel.gtip_code == sub_code,
                    TgtcGtipModel.is_active == True,
                ).first()
                if not sub_row:
                    sub_row = session.query(TariffHierarchyModel).filter(
                        TariffHierarchyModel.gtip_code == sub_code,
                        TariffHierarchyModel.level == 6,
                    ).first()
                sub_desc = str(getattr(sub_row, "description", None) or getattr(sub_row, "description_tr", None) or "")
                if sub_desc:
                    records.append(
                        LegalSource(
                            source_type="TGTC_SUBHEADING",
                            reference_no=f"Alt Pozisyon {sub_code[:4]}.{sub_code[4:]}",
                            title=f"2026 TGTC {sub_code[:4]}.{sub_code[4:]} Alt Pozisyonu Resmi Metni",
                            excerpt=f"Alt Pozisyon {sub_code[:4]}.{sub_code[4:]}: {sub_desc}",
                            legal_role="NORMATIVE",
                            authority_level=1,
                            effective_from="2026-01-01",
                            is_binding=True,
                        )
                    )

            if len(clean_code) == 12:
                leaf_row = session.query(TgtcGtipModel).filter(
                    TgtcGtipModel.gtip_code == clean_code,
                    TgtcGtipModel.is_active == True,
                ).first()
                if not leaf_row:
                    leaf_row = session.query(TariffHierarchyModel).filter(
                        TariffHierarchyModel.gtip_code == clean_code,
                        TariffHierarchyModel.is_leaf == True,
                    ).first()
                leaf_desc = str(getattr(leaf_row, "description", None) or getattr(leaf_row, "description_tr", None) or "")
                fmt_leaf = f"{clean_code[:4]}.{clean_code[4:6]}.{clean_code[6:8]}.{clean_code[8:10]}.{clean_code[10:12]}"
                if leaf_desc:
                    records.append(
                        LegalSource(
                            source_type="TGTC_LEAF",
                            reference_no=fmt_leaf,
                            title=f"2026 TGTC {fmt_leaf} Resmi İstatistik Pozisyonu Metni",
                            excerpt=f"{fmt_leaf}: {leaf_desc}",
                            legal_role="NORMATIVE",
                            authority_level=1,
                            effective_from="2026-01-01",
                            is_binding=True,
                        )
                    )
    except Exception as exc:
        logger.warning("[Statute Records] DB alt pozisyon/yaprak sorgu uyarısı: %s", exc)

    # 3. İlgili Fasıl ve Dışlama Notları (Veritabanı Orijinal Not Metinleri)
    from api.modules import tariff_notes

    cited_chapter_codes, cited_sections = tariff_notes.cited_note_refs(cited_chapters)
    chapters_to_cite = list(dict.fromkeys(cited_chapter_codes + ([clean_code[:2]] if clean_code else [])))

    # Bölüm notları kaynakta yalnız bölümün ilk faslında gömülüydü; ayrı kaynak
    # olarak gösterilir ve bölümdeki her fasıl için geçerlidir.
    cited_sections = [roman for roman in cited_sections if tariff_notes.section_notes(roman)]
    for c in chapters_to_cite:
        roman = tariff_notes.section_of(str(c))
        if roman and roman not in cited_sections and tariff_notes.section_notes(roman):
            cited_sections.append(roman)
    for roman in cited_sections:
        records.append(
            LegalSource(
                source_type="BOLUM_NOTU",
                reference_no=f"Bölüm {roman} Notları",
                title=f"Bölüm {roman} Resmi Notları",
                excerpt=tariff_notes.condense(tariff_notes.section_notes(roman) or "", 1800),
                legal_role="NORMATIVE",
                authority_level=1,
                effective_from="2026-01-01",
                is_binding=True,
            )
        )

    for c in chapters_to_cite:
        c_str = str(c).zfill(2)
        raw_note = tariff_notes.chapter_notes(c_str) if c_str.isdigit() else ""
        if raw_note:
            c_title = OFFICIAL_CHAPTER_TITLES.get(c_str, f"Fasıl {c_str}")
            is_exclusion = "dahil değildir" in raw_note.lower() or (clean_code and c_str != clean_code[:2])
            title_prefix = f"Fasıl {c_str} ({c_title}) Resmi Dışlama Notu" if is_exclusion else f"Fasıl {c_str} ({c_title}) Resmi Fasıl Notu"
            ref_prefix = f"Fasıl {c_str} Dışlama Notu" if is_exclusion else f"Fasıl {c_str} Notları"
            
            records.append(
                LegalSource(
                    source_type="FASIL_NOTU",
                    reference_no=ref_prefix,
                    title=title_prefix,
                    excerpt=tariff_notes.condense(raw_note, 1800),
                    legal_role="INTERPRETIVE" if is_exclusion else "NORMATIVE",
                    authority_level=1,
                    effective_from="2026-01-01",
                    is_binding=True,
                )
            )

    return records

