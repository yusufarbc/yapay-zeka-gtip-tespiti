"""
Resmi Türk Gümrük Tarife Cetveli (TGTC) 99 Fasıl Mevzuat ve İzahname Önbelleği (Context Cache Store).
4458 Sayılı Gümrük Kanunu, GİR Kuralları 1-6 ve 21 Bölüm / 99 Fasıl Tam GTİP Veri Tabanı.
"""
import re
from typing import Dict, List

KEYWORD_CHAPTER_MAP = {
    # 01-05: Canlı Hayvanlar ve Hayvansal Ürünler
    "sigir": "01", "sığır": "01", "dana": "01", "tavuk": "01", "civciv": "01", "koyun": "01",
    "et": "02", "biftek": "02", "kıyma": "02", "biftek": "02", "kanat": "02",
    "balik": "03", "balık": "03", "somon": "03", "karides": "03", "hamsi": "03", "levrek": "03",
    "sut": "04", "süt": "04", "peynir": "04", "bal": "04", "yumurta": "04", "tereyag": "04", "tereyağı": "04",

    # 06-14: Bitkisel ve Tarımsal Ürünler
    "cicek": "06", "çiçek": "06", "orkide": "06", "fidan": "06", "bitki": "06",
    "sebze": "07", "patates": "07", "domates": "07", "sogan": "07", "soğan": "07",
    "meyve": "08", "elma": "08", "portakal": "08", "muz": "08", "fındık": "08", "findik": "08",
    "kahve": "09", "cay": "09", "çay": "09", "karabiber": "09", "baharat": "09",
    "bugday": "10", "buğday": "10", "misir": "10", "mısır": "10", "pirinc": "10", "pirinç": "10", "hububat": "10",
    "un": "11", "nisasta": "11", "nişasta": "11", "malt": "11",
    "soya": "12", "tohum": "12", "aycicegi": "12", "ayçiçeği": "12",
    "bitkisel ozut": "13", "bitkisel özüt": "13", "zamk": "13",

    # 15-24: Yağlar, Gıdalar, İçecekler, Tütün
    "zeytinyag": "15", "zeytinyağı": "15", "aycicek yagi": "15", "ayçiçek yağı": "15", "yag": "15", "yağ": "15",
    "konserve": "16", "ton baligi": "16", "ton balığı": "16",
    "seker": "17", "şeker": "17", "sakkaroz": "17", "glukoz": "17",
    "cikolata": "18", "çikolata": "18", "kakao": "18",
    "biskuvi": "19", "bisküvi": "19", "gofret": "19", "makarna": "19", "ekmek": "19",
    "salca": "20", "salça": "20", "meyve suyu": "20", "recel": "20", "reçel": "20",
    "gida takviyesi": "21", "gıda takviyesi": "21", "vitamin": "21", "sos": "21",
    "gazoz": "22", "kola": "22", "mesrubat": "22", "meşrubat": "22", "su": "22", "sarap": "22", "şarap": "22", "bira": "22",
    "yem": "23", "kedi mamasi": "23", "kedi maması": "23", "kopek mamasi": "23", "köpek maması": "23",
    "sigara": "24", "tutun": "24", "tütün": "24",

    # 25-38: Mineraller, Kimyasallar, İlaç, Parfüm, Gübre
    "cimento": "25", "çimento": "25", "tuz": "25", "alci": "25", "alçı": "25", "mermer ham": "25",
    "cevher": "26", "demir cevheri": "26",
    "benzin": "27", "dizel": "27", "motorin": "27", "petrol": "27", "madeni yag": "27", "madeni yağ": "27", "gres": "27",
    "hidrojen": "28", "oksijen": "28", "asit": "28", "sodyum": "28",
    "metanol": "29", "alkol": "29", "organik kimyasal": "29",
    "ilac": "30", "ilaç": "30", "parasetamol": "30", "asi": "30", "aşı": "30", "tablet": "30", "serum": "30",
    "gubre": "31", "gübre": "31", "ure": "31", "üre": "31", "azotlu gubre": "31",
    "boya": "32", "cila": "32", "pigment": "32", "murekkep": "32", "mürekkep": "32",
    "parfum": "33", "parfüm": "33", "kozmetik": "33", "krem": "33", "losyon": "33", "sampuan": "33", "şampuan": "33",
    "deterjan": "34", "sabun": "34", "yikama": "34", "yıkama": "34",
    "tutkal": "35", "yapistirici": "35", "yapıştırıcı": "35", "enzim": "35",
    "patlayici": "36", "patlayıcı": "36", "kibrit": "36",
    "fotograf": "37", "fotoğraf": "37", "film plaka": "37",
    "bocek ilaci": "38", "böcek ilacı": "38", "dezenfektan": "38", "kimyasal": "38",

    # 39-49: Plastik, Kauçuk, Deri, Ahşap, Kağıt
    "plastik": "39", "polietilen": "39", "polipropilen": "39", "pvc": "39", "pet saklama": "39", "plastik kap": "39",
    "lastik": "40", "kaucuk": "40", "kauçuk": "40", "oto lastigi": "40", "oto lastiği": "40",
    "deri ham": "41", "vidala": "41", "post": "41",
    "cant": "42", "çant": "42", "cuzdan": "42", "cüzdan": "42", "bavul": "42", "saraciye": "42", "deri canta": "42",
    "kurk": "43", "kürk": "43",
    "ahsap": "44", "ahşap": "44", "kereste": "44", "kontrplak": "44", "odun": "44",
    "mantar": "45", "tapa": "45",
    "bambu": "46", "hasir": "46", "hasır": "46", "sepet": "46",
    "seluloz": "47", "selüloz": "47", "kagit hamuru": "47",
    "kagit": "48", "kağıt": "48", "karton": "48", "tuvalet kagidi": "48", "tuvalet kağıdı": "48", "kutu kagit": "48",
    "kitap": "49", "dergi": "49", "gazete": "49", "baski": "49", "baskı": "49",

    # 50-63: Tekstil, Kumaş, Giyim
    "ipek": "50",
    "yun": "51", "yün": "51",
    "pamuk": "52", "pamuklu": "52",
    "keten": "53",
    "filament": "54", "polyester kumaş": "54",
    "sentetik kumaş": "55",
    "nonwoven": "56", "tela": "56", "kece": "56", "keçe": "56", "halat": "56",
    "hali": "57", "halı": "57", "kilim": "57",
    "dantel": "58", "kurdele": "58", "serit": "58", "şerit": "58",
    "branda": "59", "kaplama kumas": "59",
    "orme kumas": "60", "örme kumaş": "60", "suprem": "60", "süprem": "60",
    "t-shirt": "61", "tshirt": "61", "tişört": "61", "kazak": "61", "orme giyim": "61", "örme giyim": "61",
    "pantolon": "62", "ceket": "62", "takim elbise": "62", "takım elbise": "62", "kaban": "62", "dokuma giyim": "62",
    "nevresim": "63", "yatak ortusu": "63", "yatak örtüsü": "63", "havlu": "63", "perde": "63",

    # 64-83: Ayakkabı, Seramik, Cam, Metaller, Aletler
    "ayakkab": "64", "ayakkabı": "64", "ayakkabi": "64", "bot": "64", "terlik": "64", "cizme": "64", "çizme": "64", "sandalet": "64",
    "sapka": "65", "şapka": "65", "kask": "65", "bere": "65",
    "semsiye": "66", "şemsiye": "66",
    "yapay cicek": "67", "yapay çiçek": "67",
    "mermer": "68", "tas karo": "68", "taş karo": "68", "cimento esya": "68",
    "seramik": "69", "porselen": "69", "fayans": "69", "karo": "69",
    "cam": "70", "zuccaciye": "70", "züccaciye": "70", "sise": "70", "şişe": "70", "cam yunu": "70",
    "altin": "71", "altın": "71", "gumus": "71", "gümüş": "71", "mücevher": "71", "mucevher": "71", "yüzük": "71",
    "celik": "72", "çelik": "72", "demir": "72", "sac": "72",
    "boru": "73", "profil": "73", "vida": "73", "civata": "73", "cıvata": "73", "celik esya": "73",
    "bakir": "74", "bakır": "74", "bakir tel": "74",
    "nikel": "75",
    "aluminyum": "76", "alüminyum": "76", "aluminyum profil": "76",
    "kursun": "78", "kurşun": "78",
    "cinko": "79", "çinko": "79",
    "kalay": "80",
    "tungsten": "81", "titanyum": "81",
    "el aleti": "82", "tornavida": "82", "pense": "82", "bicak": "82", "bıçak": "82",
    "kilit": "83", "anahtar": "83", "kasa": "83",

    # 84-85: Makineler, Bilgisayar, Elektronik
    "bilgisayar": "84", "laptop": "84", "notebook": "84", "buzdolab": "84", "buzdolabı": "84", "camasir": "84", "çamaşır": "84", "pompa": "84", "kompresor": "84", "kompresör": "84", "klima": "84", "jenerator": "84", "jeneratör": "84", "vana": "84", "rulman": "84", "motor mekanik": "84",
    "iphone": "85", "akilli": "85", "akıllı": "85", "telefon": "85", "sarj": "85", "şarj": "85", "batarya": "85", "aku": "85", "akü": "85", "firca": "85", "fırça": "85", "tv": "85", "televizyon": "85", "entegre": "85", "pdip": "85", "cip": "85", "çip": "85", "yari iletken": "85", "yarı iletken": "85", "transistor": "85", "transistör": "85", "mikroislemci": "85", "mikroişlemci": "85", "devre": "85", "elektronik": "85", "diyot": "85", "direnc": "85", "direnç": "85", "kondansator": "85", "kondansatör": "85", "trafo": "85", "guc kaynagi": "85", "güç kaynağı": "85", "entegre devre": "85",

    # 86-93: Taşıtlar, Tıbbi Cihazlar, Saat, Silah
    "vagon": "86", "lokomotif": "86", "ray": "86",
    "arab": "87", "bisiklet": "87", "otomobil": "87", "tasit": "87", "taşıt": "87", "motosiklet": "87", "skuter": "87", "traktor": "87", "traktör": "87", "kamyon": "87", "otobus": "87", "otobüs": "87",
    "drone": "88", "ucak": "88", "uçak": "88", "helikopter": "88",
    "gemi": "89", "tekne": "89", "yat": "89", "bot": "89",
    "ultrason": "90", "tibbi": "90", "tıbbi": "90", "cerrahi": "90", "mr cihaz": "90", "rontgen": "90", "röntgen": "90", "gozluk": "90", "gözlük": "90", "mikroskop": "90", "teleskop": "90",
    "saat": "91", "kol saati": "91", "duvar saati": "91",
    "gitar": "92", "piyano": "92", "keman": "92", "muzik aleti": "92", "müzik aleti": "92",
    "silah": "93", "tufek": "93", "tüfek": "93", "tabanca": "93", "mermi": "93",

    # 94-99: Mobilya, Oyuncaklar, Çeşitli Eşya
    "mas": "94", "sandalye": "94", "mobilya": "94", "koltuk": "94", "yatak": "94", "sehpa": "94", "avize": "94", "led ampul": "94", "aydinlatma": "94", "aydınlatma": "94",
    "oyuncak": "95", "kumandali": "95", "kumandalı": "95", "yaris arabas": "95", "yarış arabas": "95", "bebek oyuncak": "95", "top": "95", "spor aleti": "95",
    "hijyenik ped": "96", "bebek bezi": "96", "tukenmez kalem": "96", "tükenmez kalem": "96", "cakmak": "96", "çakmak": "96", "fermuar": "96", "dugme": "96", "düğme": "96",
    "tablo": "97", "antika": "97", "sanat eseri": "97",
    "muafiyet": "98", "diplomatik": "99"
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
