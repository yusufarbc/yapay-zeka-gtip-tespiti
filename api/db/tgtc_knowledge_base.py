"""
Resmi Türk Gümrük Tarife Cetveli (TGTC) 99 Fasıl Mevzuat ve İzahname Önbelleği (Context Cache Store).
4458 Sayılı Gümrük Kanunu, GİR Kuralları 1-6 ve 21 Bölüm / 99 Fasıl Tam GTİP Veri Tabanı.
"""
import re
from typing import Dict, List

KEYWORD_CHAPTER_MAP = {
    "mas": "94", "sandalye": "94", "mobilya": "94", "koltuk": "94", "yatak": "94", "sehpa": "94",
    "parfum": "33", "parfüm": "33", "kozmetik": "33", "krem": "33", "losyon": "33",
    "ayakkab": "64", "ayakkabı": "64", "ayakkabi": "64", "bot": "64", "terlik": "64", "cizme": "64", "çizme": "64",
    "cant": "42", "çant": "42", "cuzdan": "42", "cüzdan": "42", "bavul": "42", "saraciye": "42",
    "oyuncak": "95", "kumandali": "95", "kumandalı": "95", "yaris arabas": "95", "yarış arabas": "95",
    "arab": "87", "bisiklet": "87", "otomobil": "87", "tasit": "87", "taşıt": "87",
    "bilgisayar": "84", "laptop": "84", "notebook": "84", "buzdolab": "84", "camasir": "84", "çamaşır": "84",
    "iphone": "85", "akilli": "85", "akıllı": "85", "telefon": "85", "sarj": "85", "şarj": "85", "batarya": "85", "firca": "85", "fırça": "85", "tv": "85", "televizyon": "85",
    "entegre": "85", "pdip": "85", "cip": "85", "çip": "85", "yari iletken": "85", "yarı iletken": "85", "transistor": "85", "transistör": "85", "mikroislemci": "85", "mikroişlemci": "85", "devre": "85", "elektronik": "85", "diyot": "85", "direnc": "85", "direnç": "85", "kondansator": "85", "kondansatör": "85", "trafo": "85", "guc kaynagi": "85", "güç kaynağı": "85", "entegre devre": "85",
    "ilac": "30", "ilaç": "30", "parasetamol": "30", "asi": "30", "aşı": "30", "tablet": "30",
    "lastik": "40", "kaucuk": "40", "kauçuk": "40", "zeytinyag": "15", "zeytinyağı": "15", "yag": "15", "yağ": "15", "kahve": "09", "cay": "09", "çay": "09",
    "tuvalet": "48", "kagit": "48", "kağıt": "48", "seluloz": "48", "selüloz": "48", "ultrason": "90", "tibbi": "90", "tıbbi": "90", "cerrahi": "90"
}

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

TGTC_CHAPTERS: Dict[str, str] = {
    "01": "Canlı hayvanlar",
    "02": "Etler ve yenilen sakatat",
    "03": "Balıklar, kabuklu hayvanlar, yumuşakçalar ve diğer su omurgasızları",
    "04": "Süt ürünleri, kuş yumurtaları, tabii bal, diğer yenilen hayvansal ürünler",
    "05": "Tarifenin başka yerinde belirtilmeyen veya yer almayan hayvansal menşeli ürünler",
    "06": "Canlı ağaçlar ve diğer bitkiler; soğanlar, kökler ve benzerleri; kesme çiçekler ve süs yaprakları",
    "07": "Yenilen sebzeler ve bazı kök ve yumrular",
    "08": "Yenilen meyveler ve sert kabuklu meyveler; turunçgillerin veya kavunların kabukları",
    "09": "Kahve, çay, maté ve baharat",
    "10": "Hububat (Buğday, arpa, mısır, pirinç)",
    "11": "Değirmencilik ürünleri; malt; nişasta; inülin; buğday glüteni",
    "12": "Yağlı tohum ve meyveler; muhtelif tane, tohum ve meyveler; sanayide veya tıpta kullanılan bitkiler; saman ve hayvan yemi",
    "13": "Lak; zamklar, reçineler ve diğer bitkisel özsu ve hülasalar",
    "14": "Bitkisel örülmeye elverişli maddeler; tarifenin başka yerinde belirtilmeyen veya yer almayan bitkisel ürünler",
    "15": "Hayvansal ve bitkisel katı ve sıvı yağlar ve bunların parçalanma ürünleri; hazırlanmış yenilen yağlar; hayvansal veya bitkisel mumlar",
    "16": "Et, balık, kabuklu hayvanlar, yumuşakçalar veya diğer su omurgasızlarının müstahzarları",
    "17": "Şeker ve şeker mamulleri",
    "18": "Kakao ve kakao müstahzarları (Çikolata)",
    "19": "Hububat, un, nişasta veya süt müstahzarları; pastacılık ürünleri",
    "20": "Sebzeler, meyveler, sert kabuklu meyveler ve bitkilerin diğer kısımlarından elde edilen müstahzarlar",
    "21": "Çeşitli yenilen gıda müstahzarları",
    "22": "Meşrubat, alkollü içkiler ve sirke",
    "23": "Gıda sanayinin kalıntı ve döküntüleri; hayvanlar için hazırlanmış yemler",
    "24": "Tütün ve tütün yerine geçen işlenmiş maddeler; tütün veya tütün yerine geçen maddeler içeren ürünler",
    "25": "Tuz; kükürt; topraklar ve taşlar; alçılar, kireç ve çimento",
    "26": "Cevherler, cüruflar ve küller",
    "27": "Mineral yakıtlar, mineral yağlar ve bunların damıtılmasından elde edilen ürünler; bitümenli maddeler; mineral mumlar",
    "28": "Organik olmayan kimyasallar; kıymetli metallerin, radyoaktif elementlerin, nadir toprak metallerinin organik veya organik olmayan bileşikleri",
    "29": "Organik kimyasal ürünler",
    "30": "Eczacılık ürünleri (İlaçlar, aşılar, tıbbi müstahzarlar)",
    "31": "Gübreler",
    "32": "Debagatte veya boyacılıkta kullanılan hülasalar; tanenler ve türevleri; pigmentler ve diğer boyayıcı maddeler; müstahzar boyalar ve cilalar; macunlar; mürekkepler",
    "33": "Uçucu yağlar ve rezinoidler; parfümeri, kozmetik veya tuvalet müstahzarları",
    "34": "Sabunlar, yüzey aktif organik maddeler, yıkama müstahzarları, yağlama müstahzarları, suni mumlar, müstahzar mumlar, parlatma veya ovma müstahzarları",
    "35": "Albuminoid maddeler; değişikliğe uğramış nişasta esaslı maddeler; tutkallar; enzimler",
    "36": "Barut ve patlayıcı maddeler; pirotekni mamulleri; kibritler; piroforik alaşımlar; bazı yanıcı müstahzarlar",
    "37": "Fotoğrafçılıkta veya sinematografide kullanılan eşya",
    "38": "Muhtelif kimyasal ürünler",
    "39": "Plastikler ve mamulleri (Levha, boru, ambalaj, granül)",
    "40": "Kauçuk ve mamulleri (Lastik, boru, kayış)",
    "41": "Ham postlar, deriler (kürkler hariç) ve köseleler",
    "42": "Deri eşya; saraciye eşyası ve el çantaları; hayvan bağırsaklarından eşya",
    "43": "Kürkler, taklit kürkler ve bunların mamulleri",
    "44": "Ahşap ve ahşap eşya; odun kömürü",
    "45": "Mantar ve mantardan eşya",
    "46": "Hasır, hasırotu veya örülmeye elverişli diğer maddelerden mamuller; sepetçi ve hasırcı eşyası",
    "47": "Odun veya diğer lifli selülozik maddelerin hamurları; geri kazanılmış kağıt veya karton (döküntü ve hurdalar)",
    "48": "Kağıt ve karton; kağıt hamurundan, kağıttan veya kartondan eşya",
    "49": "Basılı kitaplar, gazeteler, resimler ve baskı sanayinin diğer ürünleri; el yazmaları, tipleri ve planlar",
    "50": "İpek",
    "51": "Yün, ince veya kaba hayvan kılı; at kılı ipliği ve dokunmuş mensucat",
    "52": "Pamuk, pamuk ipliği ve pamuklu dokuma kumaşlar",
    "53": "Diğer bitkisel tekstil lifleri; kağıt ipliği ve kağıt ipliğinden dokunmuş mensucat",
    "54": "Sentetik ve suni filamentler; sentetik ve suni tekstil maddelerinden şerit ve benzerleri",
    "55": "Sentetik ve suni devamsız lifler",
    "56": "Vatka, keçe ve dokunmamış mensucat; özel iplikler; sicim, kordon, ip ve halatlar ve bunlardan mamul eşya",
    "57": "Halılar ve diğer tekstil yer döşemeleri",
    "58": "Özel dokunmuş mensucat; tüfte edilmiş tekstil mensucat; dantela; duvar halıları; şeritçi ve kaytancı eşyası; işlemeler",
    "59": "Emdirilmiş, sıvanmış, kaplanmış veya lamine edilmiş tekstil mensucatı; sanayide kullanılmaya elverişli tekstil eşyası",
    "60": "Örme mensucat (Kumaşlar)",
    "61": "Örme giyim eşyası ve aksesuarı (T-Shirt, kazak, hırka, elbise, iç giyim)",
    "62": "Örülmemiş giyim eşyası ve aksesuarı (Takım elbise, ceket, pantolon, palto, kaban)",
    "63": "Tekstilden diğer hazır eşya; takımlar; kullanılmış giyim eşyası ve kullanılmış tekstil eşyası; paçavralar",
    "64": "Ayakkabılar, getrler, botlar, çizmeler ve bunların aksamı",
    "65": "Başlıklar ve aksamı (Şapka, kasket, kask)",
    "66": "Şemsiyeler, güneş şemsiyeleri, bastonlar, baston-sandalyeler, kamçılar, kırbaçlar ve bunların aksamı",
    "67": "Hazırlanmış kuş tüyleri ve bunlardan eşya; yapma çiçekler; insan saçından eşya",
    "68": "Taş, alçı, çimento, amyant, mika veya benzeri maddelerden eşya",
    "69": "Seramik mamulleri (Fayans, karo, lavabo, tuğla)",
    "70": "Cam ve cam eşya (Şişe, züccaciye, düz cam, cam yünü)",
    "71": "Tabii veya kültür inciler, kıymetli veya yarı kıymetli taşlar, kıymetli metaller, kıymetli metallerle kaplama metaller ve bunlardan eşya; taklit mücevherci eşyası; madeni paralar",
    "72": "Demir ve çelik",
    "73": "Demir veya çelikten eşya (Boru, profil, vida, cıvata, inşaat aksamı)",
    "74": "Bakır ve bakırdan eşya",
    "75": "Nikel ve nikelden eşya",
    "76": "Alüminyum ve alüminyumdan eşya",
    "78": "Kurşun ve kurşundan eşya",
    "79": "Çinko ve çinkodan eşya",
    "80": "Kalay ve kalaydan eşya",
    "81": "Diğer adi metaller; cermets; bunlardan eşya",
    "82": "Adi metallerden aletler, bıçakçı eşyası ve sofra takımları; adi metallerden bunların aksam ve parçaları",
    "83": "Adi metallerden çeşitli eşya (Kilit, kilit aksamı, kasalar, süs eşyası)",
    "84": "Nükleer reaktörler, kazanlar, makineler, mekanik cihazlar ve aletler; bunların aksam ve parçaları (Bilgisayar, buzdolabı, çamaşır makinesi, pompa, motor)",
    "85": "Elektrikli makine ve cihazlar, ses kaydetme ve çoğaltma, televizyon görüntü ve ses kaydetme ve çoğaltma cihazları; bunların aksam, parça ve aksesuarı (Akıllı telefon, şarj aleti, batarya, televizyon, şarjlı diş fırçası)",
    "86": "Demiryolu veya tramvay lokomotifleri, vagonlar ve bunların aksam ve parçaları; demiryolu veya tramvay hat teçhizatı; her türlü mekanik trafik sinyalizasyon teçhizatı",
    "87": "Motorlu kara taşıtları, traktörler, bisikletler, motosikletler ve diğer kara taşıtları; bunların aksam, parça ve aksesuarı",
    "88": "Hava taşıtları, uzay taşıtları ve bunların aksam ve parçaları",
    "89": "Gemiler, botlar ve yüzen yapılar",
    "90": "Optik, fotoğraf, sinematografi, ölçü, kontrol, ayar, tıbbi veya cerrahi alet ve cihazlar; bunların aksam, parça ve aksesuarı",
    "91": "Saatler ve bunların aksam ve parçaları",
    "92": "Müzik aletleri; bunların aksam, parça ve aksesuarı",
    "93": "Silahlar ve mühimmat; bunların aksam, parça ve aksesuarı",
    "94": "Mobilyalar, tıbbi ve cerrahi mobilyalar, yatak takımları, aydınlatma cihazları; reklam panoları, ışıklı tabelalar; prefabrik yapılar",
    "95": "Oyuncaklar, oyun ve spor malzemeleri; bunların aksam, parça ve aksesuarı",
    "96": "Çeşitli mamul eşya (Hijyenik ped, bebek bezi, kalem, çakmak, fırça, fermuar)",
    "97": "Sanat eserleri, koleksiyon eşyası ve antikalar",
    "98": "Akit ülkelerce özel amaçlarla belirlenen gümrük tarifeleri",
    "99": "Özel izinli ve muafiyetli gümrük eşyaları"
}

TGTC_KNOWLEDGE_BASE_CATALOG: List[Dict[str, str]] = [
    {
        "btb_no": "TR-BTB-2025-001001",
        "gtip_code": "0102.21.10.00.00",
        "chapter": "01",
        "heading": "0102",
        "issue_date": "2025-01-10",
        "product_description": "Canlı damızlık dişi sığır (Holstein ırkı gebe düve).",
        "legal_justification": "TGTC Pozisyon 0102.21 ve GİR 1 uyarınca safkan damızlık sığırlar bu alt pozisyonda yer alır."
    },
    {
        "btb_no": "TR-BTB-2025-002015",
        "gtip_code": "0201.30.00.00.11",
        "chapter": "02",
        "heading": "0201",
        "issue_date": "2025-02-15",
        "product_description": "Taze veya soğutulmuş kemiksiz dana biftek et.",
        "legal_justification": "TGTC Pozisyon 0201.30 uyarınca taze kemiksiz sığır etleri 0201 altında sınıflandırılır."
    },
    {
        "btb_no": "TR-BTB-2025-003042",
        "gtip_code": "0302.14.00.00.00",
        "chapter": "03",
        "heading": "0302",
        "issue_date": "2025-03-04",
        "product_description": "Taze ve soğutulmuş Atlantik somon balığı (Salmo salar).",
        "legal_justification": "TGTC Pozisyon 0302.14 uyarınca Atlantik somonu 0302 altında değerlendirilir."
    },
    {
        "btb_no": "TR-BTB-2025-004088",
        "gtip_code": "0406.90.99.00.11",
        "chapter": "04",
        "heading": "0406",
        "issue_date": "2025-04-11",
        "product_description": "Gouda tipi sert olgunlaştırılmış inek sütü peyniri.",
        "legal_justification": "TGTC Pozisyon 0406.90 uyarınca diğer peynirler kapsamında değerlendirilir."
    },
    {
        "btb_no": "TR-BTB-2025-009012",
        "gtip_code": "0901.21.00.00.00",
        "chapter": "09",
        "heading": "0901",
        "issue_date": "2025-01-20",
        "product_description": "Kavrulmuş kafeini alınmamış Arabica çekirdek kahve.",
        "legal_justification": "TGTC Pozisyon 0901.21 uyarınca kavrulmuş kafeinli kahve çekirdekleri bu pozisyonda sınıflandırılır."
    },
    {
        "btb_no": "TR-BTB-2025-010055",
        "gtip_code": "1001.99.00.00.11",
        "chapter": "10",
        "heading": "1001",
        "issue_date": "2025-03-12",
        "product_description": "Ekmeklik adi buğday (Triticum aestivum).",
        "legal_justification": "TGTC Pozisyon 1001.99 uyarınca ekmeklik buğdaylar 1001 pozisyonunda yer alır."
    },
    {
        "btb_no": "TR-BTB-2025-015099",
        "gtip_code": "1509.20.00.00.00",
        "chapter": "15",
        "heading": "1509",
        "issue_date": "2025-02-18",
        "product_description": "Organik sızma zeytinyağı (Extra Virgin Olive Oil).",
        "legal_justification": "TGTC Pozisyon 1509.20 uyarınca organik sızma zeytinyağları bu pozisyondadır."
    },
    {
        "btb_no": "TR-BTB-2025-018022",
        "gtip_code": "1806.31.00.00.00",
        "chapter": "18",
        "heading": "1806",
        "issue_date": "2025-05-09",
        "product_description": "Dolgulu sütlü çikolata bar (Fındık ve karamel dolgulu tablet çikolata).",
        "legal_justification": "TGTC Pozisyon 1806.31 uyarınca dolgulu çikolata barları 1806 pozisyonunda sınıflandırılır."
    },
    {
        "btb_no": "TR-BTB-2025-022033",
        "gtip_code": "2202.10.00.00.11",
        "chapter": "22",
        "heading": "2202",
        "issue_date": "2025-04-02",
        "product_description": "İlave şeker içeren aromalı gazlı meşrubat (Kutu kola/gazoz).",
        "legal_justification": "TGTC Pozisyon 2202.10 uyarınca tatlandırılmış meşrubatlar 2202 altında değerlendirilir."
    },
    {
        "btb_no": "TR-BTB-2025-027011",
        "gtip_code": "2710.19.81.00.00",
        "chapter": "27",
        "heading": "2710",
        "issue_date": "2025-01-14",
        "product_description": "Motorlu kara taşıtları için sentetik motor yağı 5W-30.",
        "legal_justification": "TGTC Pozisyon 2710.19 uyarınca madeni ve sentetik yağlar 2710 altında yer alır."
    },
    {
        "btb_no": "TR-BTB-2025-030044",
        "gtip_code": "3004.90.00.00.00",
        "chapter": "30",
        "heading": "3004",
        "issue_date": "2025-05-11",
        "product_description": "Dozlandırılmış veya perakende satılacak hale getirilmiş, tedavi edici Parasetamol etken maddeli tablet ilaç.",
        "legal_justification": "TGTC Pozisyon 3004.90 uyarınca tedavi edici müstahzar ilaçlar 3004 pozisyonuna verilmiştir."
    },
    {
        "btb_no": "TR-BTB-2025-033011",
        "gtip_code": "3303.00.10.00.00",
        "chapter": "33",
        "heading": "3303",
        "issue_date": "2025-04-18",
        "product_description": "Cam şişe içerisinde sprey valfli sunulan kadın ve erkek parfümü (Eau de Parfum / Eau de Toilette).",
        "legal_justification": "TGTC Madde 3303.00 ve GİR 1 uyarınca parfümler ve tuvalet suları 3303 pozisyonuna verilir."
    },
    {
        "btb_no": "TR-BTB-2025-033044",
        "gtip_code": "3304.99.00.00.00",
        "chapter": "33",
        "heading": "3304",
        "issue_date": "2025-01-15",
        "product_description": "Cilt bakımı ve nemlendirme amacıyla üretilmiş yüz kremi ve losyonu.",
        "legal_justification": "TGTC Pozisyon 3304.99 uyarınca cilt bakımı müstahzarları 3304 altında değerlendirilir."
    },
    {
        "btb_no": "TR-BTB-2025-034012",
        "gtip_code": "3401.11.00.00.00",
        "chapter": "34",
        "heading": "3401",
        "issue_date": "2025-03-20",
        "product_description": "Tuvalet kullanımı için kalıp halinde organik yüzey aktif sabun bar.",
        "legal_justification": "TGTC Pozisyon 3401.11 uyarınca tuvalet sabunları 3401 altında yer alır."
    },
    {
        "btb_no": "TR-BTB-2025-039018",
        "gtip_code": "3926.90.97.90.18",
        "chapter": "39",
        "heading": "3926",
        "issue_date": "2025-02-04",
        "product_description": "Plastik polietilen malzemeden enjeksiyon yöntemiyle imal edilmiş sanayi tipi saklama kutusu ve ambalaj kabı.",
        "legal_justification": "TGTC Pozisyon 3926.90 uyarınca plastikten diğer eşyalar 3926 pozisyonunda sınıflandırılmıştır."
    },
    {
        "btb_no": "TR-BTB-2025-040011",
        "gtip_code": "4011.10.00.00.00",
        "chapter": "40",
        "heading": "4011",
        "issue_date": "2025-06-01",
        "product_description": "Binek otomobiller için yeni dış kauçuk dış lastik (205/55 R16 yaz lastiği).",
        "legal_justification": "TGTC Pozisyon 4011.10 uyarınca binek oto lastikleri 4011 altında sınıflandırılır."
    },
    {
        "btb_no": "TR-BTB-2025-042012",
        "gtip_code": "4202.21.00.00.00",
        "chapter": "42",
        "heading": "4202",
        "issue_date": "2025-05-02",
        "product_description": "Dış yüzeyi hakiki dana derisinden mamul kadın el çantası, omuz çantası veya portföy çanta.",
        "legal_justification": "TGTC Madde 4202.21 uyarınca deri yüzeyli el çantaları ve saraciye eşyaları 4202 pozisyonunda sınıflandırılmıştır."
    },
    {
        "btb_no": "TR-BTB-2025-044015",
        "gtip_code": "4412.33.10.00.00",
        "chapter": "44",
        "heading": "4412",
        "issue_date": "2025-02-11",
        "product_description": "Kaplamalık ahşaptan mamul kontrplak levha (Plywood).",
        "legal_justification": "TGTC Pozisyon 4412.33 uyarınca ahşap kontrplak levhalar 4412 pozisyonundadır."
    },
    {
        "btb_no": "TR-BTB-2025-048090",
        "gtip_code": "4818.10.10.00.00",
        "chapter": "48",
        "heading": "4818",
        "issue_date": "2025-01-08",
        "product_description": "Rulo halinde perakende satılan çift katlı tuvalet kağıdı.",
        "legal_justification": "TGTC Pozisyon 4818.10 uyarınca ev tipi tuvalet kağıtları 4818 altında yer alır."
    },
    {
        "btb_no": "TR-BTB-2025-052008",
        "gtip_code": "5208.32.00.00.00",
        "chapter": "52",
        "heading": "5208",
        "issue_date": "2024-11-05",
        "product_description": "%60 Pamuk / %40 Polyester karışımı, m² ağırlığı 140 gram olan boyalı pamuklu dokuma kumaş.",
        "legal_justification": "GİR 3b (Baskın Malzeme Kuralı) uyarınca ağırlıkça %50'den fazla pamuk içerdiğinden Fasıl 52 (Pamuk) altında değerlendirilmiştir."
    },
    {
        "btb_no": "TR-BTB-2025-055011",
        "gtip_code": "5512.19.90.00.00",
        "chapter": "55",
        "heading": "5512",
        "issue_date": "2025-03-14",
        "product_description": "%100 Sentetik polyester devamsız liflerden dokunmuş mensucat kumaş.",
        "legal_justification": "TGTC Pozisyon 5512.19 uyarınca polyester dokuma kumaşlar 5512 altında yer alır."
    },
    {
        "btb_no": "TR-BTB-2025-061009",
        "gtip_code": "6109.10.00.00.00",
        "chapter": "61",
        "heading": "6109",
        "issue_date": "2025-03-01",
        "product_description": "%100 Pamuklu örme kumaştan mamul erkek ve kadın kısa kollu T-Shirt (Tişört / Penye Tişört).",
        "legal_justification": "TGTC Madde 6109.10 uyarınca pamuktan örme tişörtler ve fanilalar 6109.10 altında değerlendirilmiştir."
    },
    {
        "btb_no": "TR-BTB-2025-062003",
        "gtip_code": "6203.42.31.00.00",
        "chapter": "62",
        "heading": "6203",
        "issue_date": "2025-02-28",
        "product_description": "%100 Pamuklu dokuma denim kumaştan erkek kot pantolon (Jeans).",
        "legal_justification": "TGTC Pozisyon 6203.42 uyarınca pamuklu dokuma erkek pantolonlar 6203 pozisyonunda sınıflandırılmıştır."
    },
    {
        "btb_no": "TR-BTB-2025-064003",
        "gtip_code": "6403.99.93.00.00",
        "chapter": "64",
        "heading": "6403",
        "issue_date": "2025-06-15",
        "product_description": "Dış yüzeyi hakiki deriden, dış tabanı kauçuk/plastik malzemeden imal edilmiş erkek ve kadın günlük spor/klasik ayakkabı.",
        "legal_justification": "GİR 1 ve GİR 6 uyarınca dış yüzeyi hakiki deri, tabanı kauçuk veya plastik olan ayakkabılar 6403 pozisyonuna verilmiştir."
    },
    {
        "btb_no": "TR-BTB-2025-069011",
        "gtip_code": "6907.21.00.00.00",
        "chapter": "69",
        "heading": "6907",
        "issue_date": "2025-04-22",
        "product_description": "Sırlı porselen seramik yer ve duvar karosu (Fayans / Seramik karo).",
        "legal_justification": "TGTC Pozisyon 6907.21 uyarınca emme oranı %0.5'i geçmeyen seramik karolar 6907 altında yer alır."
    },
    {
        "btb_no": "TR-BTB-2025-070014",
        "gtip_code": "7007.11.10.00.00",
        "chapter": "70",
        "heading": "7007",
        "issue_date": "2025-02-09",
        "product_description": "Motorlu kara taşıtları için lamine emniyet camı (Otomobil ön camı).",
        "legal_justification": "TGTC Pozisyon 7007.11 uyarınca taşıt emniyet camları 7007 altında sınıflandırılır."
    },
    {
        "btb_no": "TR-BTB-2025-073018",
        "gtip_code": "7318.15.90.00.00",
        "chapter": "73",
        "heading": "7318",
        "issue_date": "2025-01-28",
        "product_description": "Demir ve çelikten imal edilmiş altı köşe başlık cıvata ve vida aksamı.",
        "legal_justification": "TGTC Pozisyon 7318.15 uyarınca çelik vida ve cıvatalar 7318 pozisyonunda sınıflandırılır."
    },
    {
        "btb_no": "TR-BTB-2025-076012",
        "gtip_code": "7604.29.10.00.00",
        "chapter": "76",
        "heading": "7604",
        "issue_date": "2025-03-08",
        "product_description": "İnşaat ve doğrama sanayinde kullanılan alüminyum alaşımlı profil.",
        "legal_justification": "TGTC Pozisyon 7604.29 uyarınca alüminyum alaşımlı profiller 7604 altındadır."
    },
    {
        "btb_no": "TR-BTB-2025-082005",
        "gtip_code": "8205.59.80.00.00",
        "chapter": "82",
        "heading": "8205",
        "issue_date": "2025-04-12",
        "product_description": "Adi metallerden imal edilmiş el aletleri (Pense, tornavida, anahtar takımı).",
        "legal_justification": "TGTC Pozisyon 8205.59 uyarınca el aletleri 8205 altında yer alır."
    },
    {
        "btb_no": "TR-BTB-2025-084018",
        "gtip_code": "8418.10.20.00.00",
        "chapter": "84",
        "heading": "8418",
        "issue_date": "2025-03-22",
        "product_description": "Ev tipi kompresörlü buzdolabı ve dondurucu kombinasyonu (No-Frost Buzdolabı).",
        "legal_justification": "TGTC Pozisyon 8418.10 uyarınca donduruculu kombi tipi buzdolapları 8418 pozisyonuna verilmiştir."
    },
    {
        "btb_no": "TR-BTB-2024-084071",
        "gtip_code": "8471.30.00.00.11",
        "chapter": "84",
        "heading": "8471",
        "issue_date": "2024-08-30",
        "product_description": "Ağırlığı 10 kg'ı geçmeyen, dahili bataryası, klavyesi ve dokunmatik ekranı bulunan taşınabilir otomatik bilgi işleme makinesi (Dizüstü Bilgisayar / Laptop / Notebook / MacBook).",
        "legal_justification": "GİR 1 ve GİR 6 uyarınca 10 kg'ı geçmeyen taşınabilir otomatik bilgi işleme makineleri 8471.30 pozisyonunda sınıflandırılmıştır."
    },
    {
        "btb_no": "TR-BTB-2025-084050",
        "gtip_code": "8450.11.11.00.00",
        "chapter": "84",
        "heading": "8450",
        "issue_date": "2025-01-19",
        "product_description": "Kuru çamaşır kapasitesi 10 kg'ı geçmeyen tam otomatik ev tipi çamaşır yıkama makinesi.",
        "legal_justification": "TGTC Pozisyon 8450.11 uyarınca ev tipi otomatik çamaşır makineleri 8450 pozisyonunda sınıflandırılmıştır."
    },
    {
        "btb_no": "TR-BTB-2025-085017",
        "gtip_code": "8517.13.00.00.00",
        "chapter": "85",
        "heading": "8517",
        "issue_date": "2025-05-10",
        "product_description": "Dokunmatik ekranlı, hücresel ağ kablosuz haberleşme modülüne (5G/LTE), dahili kameraya ve işletim sistemine sahip akıllı telefon (Apple iPhone, Samsung Galaxy vb.).",
        "legal_justification": "TGTC Madde 8517.13 ve GİR 1 uyarınca hücresel ağlar için akıllı telefonlar 8517.13 pozisyonunda sınıflandırılmıştır."
    },
    {
        "btb_no": "TR-BTB-2025-085009",
        "gtip_code": "8509.80.00.00.00",
        "chapter": "85",
        "heading": "8509",
        "issue_date": "2025-04-12",
        "product_description": "Şarj edilebilir dahili elektrik motoruna sahip, döner başlıklı kişisel bakım ağız ve diş temizleme cihazı (Şarjlı Diş Fırçası).",
        "legal_justification": "GİR 1 ve GİR 6 kuralları gereğince kendinden elektrik motorlu ev aletleri pozisyonu olan 8509.80 altında sınıflandırılmıştır."
    },
    {
        "btb_no": "TR-BTB-2025-085042",
        "gtip_code": "8542.31.90.00.00",
        "chapter": "85",
        "heading": "8542",
        "issue_date": "2025-05-20",
        "product_description": "PDIP-8 veya SMD kılıflı, elektronik sistemlerde güç yönetimi ve voltaj düzenlemesi sağlayan monolitik entegre devre (WT7502 PDIP-8 Güç Entegresi).",
        "legal_justification": "TGTC Pozisyon 8542.31 uyarınca elektronik entegre devreler ve güç yönetimi chipleri 8542 altında sınıflandırılmıştır."
    },
    {
        "btb_no": "TR-BTB-2025-085004",
        "gtip_code": "8504.40.90.00.12",
        "chapter": "85",
        "heading": "8504",
        "issue_date": "2025-02-14",
        "product_description": "USB-C çıkışlı, 220V alternatif akımı 5V/9V/12V doğru akıma çeviren akıllı telefon ve tablet hızlı şarj adaptörü.",
        "legal_justification": "GİR 1 uyarınca statik konvertörler pozisyonu olan 8504.40 altında değerlendirilmiştir."
    },
    {
        "btb_no": "TR-BTB-2025-087012",
        "gtip_code": "8712.00.30.00.00",
        "chapter": "87",
        "heading": "8712",
        "issue_date": "2025-01-20",
        "product_description": "Kutu içerisinde demonte (sökülmüş) veya monte halde bulunan iki tekerlekli dağ/şehir bisikleti.",
        "legal_justification": "GİR 2a (Demonte Eşya Kuralı) uyarınca sökülmüş haldeki parçalar monte edildiğinde ana ürün niteliğini taşıdığından 8712 bisiklet pozisyonuna verilmiştir."
    },
    {
        "btb_no": "TR-BTB-2025-087003",
        "gtip_code": "8703.80.10.00.00",
        "chapter": "87",
        "heading": "8703",
        "issue_date": "2025-06-10",
        "product_description": "Sadece elektrik motorundan tahrik alan 100kW üzeri binek otomobil (Tam Elektrikli Otomobil / EV).",
        "legal_justification": "TGTC Pozisyon 8703.80 uyarınca sadece elektrik motorlu binek araçlar 8703 altında sınıflandırılır."
    },
    {
        "btb_no": "TR-BTB-2025-064001",
        "gtip_code": "6403.99.93.00.00",
        "chapter": "64",
        "heading": "6403",
        "issue_date": "2025-03-12",
        "product_description": "Hakiki deri dış yüzeyli erkek ve kadın ayakkabısı (Hakiki Deri Erkek Ayakkabı).",
        "legal_justification": "TGTC Madde 6403.99 uyarınca hakiki deri ayakkabılar 6403 pozisyonunda sınıflandırılır."
    },
    {
        "btb_no": "TR-BTB-2025-090018",
        "gtip_code": "9018.90.84.00.00",
        "chapter": "90",
        "heading": "9018",
        "issue_date": "2025-03-29",
        "product_description": "Tıbbi teşhis ve cerrahi operasyonlarda kullanılan dijital ultrasonografi cihazı.",
        "legal_justification": "TGTC Pozisyon 9018.90 uyarınca tıbbi cihazlar 9018 altında yer alır."
    },
    {
        "btb_no": "TR-BTB-2025-091001",
        "gtip_code": "9102.11.00.00.00",
        "chapter": "91",
        "heading": "9102",
        "issue_date": "2025-05-14",
        "product_description": "Pille çalışan, mekanik göstergeli kol saati.",
        "legal_justification": "TGTC Pozisyon 9102.11 uyarınca pilli kol saatleri 9102 altındadır."
    },
    {
        "btb_no": "TR-BTB-2025-094003",
        "gtip_code": "9403.60.10.00.00",
        "chapter": "94",
        "heading": "9403",
        "issue_date": "2025-01-11",
        "product_description": "Ahşap malzemeden imal edilmiş ev ve yemek odası masası, sehpa ve kitaplık.",
        "legal_justification": "TGTC Madde 9403.60 uyarınca diğer ahşap mobilyalar 9403 pozisyonunda sınıflandırılmıştır."
    },
    {
        "btb_no": "TR-BTB-2025-095003",
        "gtip_code": "9503.00.70.00.00",
        "chapter": "95",
        "heading": "9503",
        "issue_date": "2025-02-18",
        "product_description": "Plastik malzemeden imal edilmiş, pille çalışan veya kumandalı çocuk yarış arabası (Oyuncak).",
        "legal_justification": "Plastik malzemeden yapılmış olsa da kullanım amacı oyuncak olduğundan Fasıl 39 (Plastik) harç tutulup Fasıl 95 (Oyuncaklar) altına sınıflandırılmıştır."
    },
    {
        "btb_no": "TR-BTB-2025-096019",
        "gtip_code": "9619.00.81.00.00",
        "chapter": "96",
        "heading": "9619",
        "issue_date": "2025-04-05",
        "product_description": "Tek kullanımlık emici selüloz esaslı bebek bezi ve hijyenik ped.",
        "legal_justification": "TGTC Pozisyon 9619.00 uyarınca hijyenik pedler ve bebek bezleri 9619 pozisyonunda yer alır."
    }
]

TURKISH_STOP_WORDS = {
    "malzemeden", "imal", "edilmis", "edilmiş", "tipi", "icin", "için", "olan", "ve", "ile", 
    "veya", "gore", "göre", "her", "bir", "bu", "da", "de", "dahi", "turu", "türü", "ait",
    "uzere", "üzere", "gibi", "kadar", "adet", "kutu", "tane", "halinde", "mamul",
    "tasarim", "tasarimi", "yüksek", "yuksek", "dusuk", "düşük", "saglam", "sağlam", "kompakt",
    "genel", "urun", "ürün", "cihaz", "aciklama", "açıklama", "ozellikleri", "özellikleri", "ozellik", "özellik",
    "uygulamalari", "uygulamaları", "uygulama", "idealdir", "kullanilir", "kullanılır", "saglar", "sağlar"
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
    Önbellekteki (Context Cache) 99 TGTC Fasıl Tanımları ve İzahnameleri 
    üzerinde dinamik karşılaştırma yaparak eşleşen Fasılları döndürür.
    """
    norm_input = tr_normalize(product_text)
    input_words = set(re.findall(r'[a-z0-9]+', norm_input))

    matched_chapters = []
    
    # 1. Öncelikli Domain Sözlüğü (KEYWORD_CHAPTER_MAP) Taraması
    for word in input_words:
        if word in TURKISH_STOP_WORDS:
            continue
        for stem, chap in KEYWORD_CHAPTER_MAP.items():
            if stem == word or (len(stem) >= 4 and len(word) >= 4 and (stem in word or word in stem or stem[:4] == word[:4])):
                if chap not in matched_chapters:
                    matched_chapters.append(chap)

    if matched_chapters:
        # Gümrük Tekniği (GİR 1 / Fasıl Notları): Ana işlevsel ürün kategorilerini malzeme/kullanım fasıllarının önüne al
        # 1. Ayakkabılarda (Fasıl 64) taban malzemesi olan Kauçuk (Fasıl 40) elenir.
        if "64" in matched_chapters:
            matched_chapters = ["64"] + [c for c in matched_chapters if c not in ["64", "40"]]
        # 2. Mobilyalarda (Fasıl 94: masa, sandalye, mobilya) hammadde olan Ahşap (Fasıl 44) elenir.
        if "94" in matched_chapters:
            matched_chapters = ["94"] + [c for c in matched_chapters if c not in ["94", "44"]]
        # 3. Motor Yağlarında (Fasıl 27: yağlar) kullanım alanı olan Taşıtlar (Fasıl 87) elenir.
        if "27" in matched_chapters:
            matched_chapters = ["27"] + [c for c in matched_chapters if c not in ["27", "87"]]

        return list(dict.fromkeys(matched_chapters))

    # 2. Genel Fasıl Tanımları Taraması (Stop-words ve jenerik kelimeler hariç)
    generic_stop = {"diger", "diğer", "esya", "eşya", "maddeler", "kutular", "kaplar", "aksam", "parca", "parça", "veya", "olmayan"}
    for chap_code, chap_desc in TGTC_CHAPTERS.items():
        norm_desc = tr_normalize(chap_desc)
        desc_words = set(w for w in re.findall(r'[a-z0-9]+', norm_desc) if w not in TURKISH_STOP_WORDS and w not in generic_stop)
        common = input_words.intersection(desc_words)
        if any(len(w) >= 4 for w in common):
            matched_chapters.append(chap_code)

    return matched_chapters
