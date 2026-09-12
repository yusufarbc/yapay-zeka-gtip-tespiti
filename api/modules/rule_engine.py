from __future__ import annotations
from typing import List, Dict, Tuple, Any, Optional
from api.schemas.product import ProductFeatures
from api.db.tgtc_knowledge_base import match_chapters_from_cache, load_tgtc_chapters, TGTC_CHAPTERS, get_chapter_title

# Kategori yönlendirme matrisi. Yalnız çok dar ve açık tanımlar ``exclusive``
# olabilir; genel ürün anahtar sözcükleri hukuken fasıl kilidi sayılmaz.
HARD_RULES_MATRIX = [
    {
        "keywords": [
            "elektrikli su ısıtıcı", "elektrikli su isitici", "su ısıtıcısı",
            "su isiticisi", "kettle", "electric kettle", "rezistanslı su"
        ],
        "materials": [],
        "locked_chapter": "85",
        "exclusive": True,
        "description": "Elektrikli su ısıtıcıları ve kettle tipi elektrotermik ev cihazları Fasıl 85 yönlendirmesi."
    },
    {
        "keywords": ["ayakkabı", "footwear", "bot ", "terlik", "babet", "çizme", "sneaker"],
        "materials": ["deri", "leather", "kauçuk", "tekstil", "sentetik", "plastik"],
        "locked_chapter": "64",
        "description": "Ayakkabılar, botlar, terlikler ve ayak giyecekleri Fasıl 64 yönlendirmesi."
    },
    {
        "keywords": [
            "pmic", "power management", "integrated circuit", "entegre", "mikroişlemci", "çip", "chip",
            "yarı iletken", "semiconductor", "transistör", "diyot", "devre", "pcb", "elektronik kart",
            "güç entegresi", "işlemci", "ram", "gpu", "cpu", "microcontroller", "mikrodenetleyici",
            "direnç", "kondansatör", "bobin", "röle", "anahtar", "konnektör", "akıllı telefon",
            "cep telefonu", "iphone", "televizyon", "monitör", "sensör", "batarya", "akü", "diş fırça", "şarj", "smd"
        ],
        "materials": [],
        "locked_chapter": "85",
        "description": "Elektrikli ve elektronik makine, cihaz, yarı iletkenler ve entegre devreler Fasıl 85 yönlendirmesi."
    },
    {
        "keywords": [
            "bilgisayar parçası", "ana kart", "motherboard", "donanım", "hard disk", "ssd", "hafıza",
            "yazıcı", "tarayıcı", "klima", "soğutma", "motor ", "pompa", "jeneratör", "kompresör", "kazan", "türbin", "vinç", "dozer"
        ],
        "materials": [],
        "locked_chapter": "84",
        "description": "Kazanlar, makina, mekanik cihazlar ve bilgisayar aksamları Fasıl 84 yönlendirmesi."
    },
    {
        "keywords": ["oyuncak", "oyun", "spor", "oyun konsol"],
        "materials": [],
        "locked_chapter": "95",
        "description": "Oyuncaklar, oyun ve spor malzemeleri Fasıl 95 yönlendirmesi."
    },
    {
        "keywords": ["mobilya", "koltuk", "sandalye", "masa", "yatak", "dolap", "sehpa", "komodin", "karyola", "kitaplık", "tabure", "kanepe", "divan"],
        "materials": [],
        "locked_chapter": "94",
        "exclusive": True,
        "description": "Mobilyalar ve oturmaya mahsus eşya için Fasıl 94 yönlendirmesi."
    },
    {
        "keywords": ["aydınlatma", "avize", "abajur", "aplik"],
        "materials": [],
        "locked_chapter": "94",
        "description": "Aydınlatma cihazları için Fasıl 94 aday yönlendirmesi."
    }
]

class RuleEngine:
    """
    Modül 2: Deterministik Kural Motoru (Python Logic Engine & Hard Rules Matrix).
    Türk Gümrük Tarife Yorum Kurallarını (GİR 1-6) sıralı uygular ve
    fasıl/pozisyon metinlerinden aday kapsamı üretir. Genel kategori sözcükleri
    aday yönlendirmesidir; tek başına hukuki fasıl kilidi değildir.
    """

    def apply_rules(self, features: ProductFeatures) -> Tuple[List[str], List[str]]:
        allowed_chapters = []
        applied_rules = []
        is_hard_locked = False

        text_combo = f"{features.product_name} {features.primary_material} {features.intended_use}".lower()

        # 1. GİR 1: Açık tanımdan fasıl adayı üret. Anahtar sözcük eşleşmesi
        # tek başına bağlayıcı sınıflandırma değildir; istisnalar fasıl notu ve
        # pozisyon metniyle denetlenir.
        matched_rules = []
        for rule in HARD_RULES_MATRIX:
            kw_match = any(kw in text_combo for kw in rule["keywords"])
            if kw_match:
                mat_match = not rule["materials"] or any(m in text_combo for m in rule["materials"])
                if mat_match:
                    matched_rules.append(rule)

        for rule in matched_rules:
            chap = rule["locked_chapter"]
            if chap not in allowed_chapters:
                allowed_chapters.append(chap)

        is_hard_locked = bool(
            len(matched_rules) == 1 and matched_rules[0].get("exclusive", False)
        )
        for rule in matched_rules:
            chap = rule["locked_chapter"]
            if is_hard_locked:
                applied_rules.append(
                    f"GİR 1 [HARD LOCK]: {rule['description']} (Fasıl {chap} dışı aramalar engellendi)."
                )
            else:
                applied_rules.append(
                    f"GİR 1 [GUIDED ROUTE]: {rule['description']} Fasıl {chap} aday kapsama alındı; "
                    "fasıl/pozisyon notları doğrulanmadan kilitlenmedi."
                )

        # 2. GİR 2a: Demonte / Sökülmüş veya Eksik Eşya Kuralı
        if features.is_disassembled or "demonte" in text_combo or "sökülmüş" in text_combo or "parça halinde" in text_combo:
            applied_rules.append("GİR 2a: Demonte/sökülmüş eşya kuralı uyarınca komple monte eşyanın faslı esas alındı.")

        # 3. GİR 3a & 3b: Karışımlar ve Esas Niteliği Veren Madde (Essential Character)
        if not is_hard_locked:
            if features.composition_percentages:
                for mat_name, ratio in features.composition_percentages.items():
                    if ratio >= 0.50:
                        matched_chaps = match_chapters_from_cache(mat_name)
                        for chap in matched_chaps:
                            if chap not in allowed_chapters:
                                allowed_chapters.append(chap)
                        if matched_chaps:
                            applied_rules.append(
                                f"GİR 3b (Essential Character): %{int(ratio*100)}+ {mat_name.title()} esas nitelik veren malzeme sebebiyle "
                                f"Fasıl {', '.join(matched_chaps)} eşleştirildi."
                            )

            # Dinamik TGTC Tanımları ile GİR 1 / GİR 3a eşleme
            cached_matches = match_chapters_from_cache(text_combo)
            for chap in cached_matches:
                if chap not in allowed_chapters:
                    allowed_chapters.append(chap)

        # 4. GİR 4: En Yakın Eşya Kuralı (Fallback Mode) - Açık Vektör Arama
        if not allowed_chapters:
            applied_rules.append("GİR 4: Doğrudan mevzuat tanımı bulunamayan özel ürün için işlev ve nitelik bakımından genel vektör uzayında tarama yapıldı.")

        # 5. GİR 6: Alt Pozisyon Kuralları ve Mevzuat Doğrulaması
        if allowed_chapters:
            chap_names = [f"Fasıl {c} ({get_chapter_title(c)})" for c in allowed_chapters[:3]]
            if is_hard_locked:
                applied_rules.append(f"GİR 6: Katı kural zırhıyla kilitlenen hedef fasıl: {', '.join(chap_names)}.")
            else:
                applied_rules.append(f"GİR 6: TGTC fasıl ve alt pozisyon metinlerine göre dinamik belirlenen fasıllar: {', '.join(chap_names)}.")

        return allowed_chapters, applied_rules

    def resolve_gyk3_conflict(
        self,
        candidate_headings: List[Dict[str, Any]],
        features: ProductFeatures,
    ) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        """
        GYK 3(a, b, c) Çatışma Çözücü Motoru (4 Haneli Pozisyon Seviyesi).
        Birden fazla 4 haneli pozisyona girebilecek eşyalarda öncelik sırası:
        1. GYK 3(a): En özel tanımı veren pozisyon, genel tanımı verene tercih edilir.
           Örn: Kulaklık için 85.18 (doğrudan kulaklık) vs 85.17 (ses/veri ileten diğer cihazlar) -> 85.18 seçilir.
        2. GYK 3(b): Esas niteliği veren madde / bileşen (karışımlar, bileşik eşya ve perakende setler için).
        3. GYK 3(c): Eşit derecede geçerli pozisyonlar arasında numara sırasına göre en sonda yer alan pozisyon.
        """
        if not candidate_headings:
            return None, []

        applied_rules = []
        text_corpus = (
            f"{features.product_name} {getattr(features, 'commercial_name', '') or ''} "
            f"{features.primary_material or ''} {features.intended_use or ''} "
            f"{getattr(features, 'function', '') or ''} {' '.join(features.keywords if hasattr(features, 'keywords') and features.keywords else [])}"
        ).lower()

        # Bilinen GYK 3(a) Özel Tanım Çiftleri Sözlüğü
        # (Genel Pozisyon, Özel Pozisyon, Gerekçe, Anahtar Kelimeler)
        SPECIFIC_HEADINGS_MAP = [
            {
                "general_heading": "8517",
                "specific_heading": "8518",
                "keywords": ["kulaklık", "headphone", "earphone", "mikrofon", "hoparlör", "speaker"],
                "reason": "GYK 3(a): 85.18 pozisyonu 'kulaklıklar, mikrofonlar ve hoparlörleri' ismen ve özel olarak tanımlar; "
                          "85.17'deki 'ses/görüntü iletimine mahsus genel cihazlar' tanımına tercih edilir."
            },
            {
                "general_heading": "8543",
                "specific_heading": "8528",
                "keywords": ["monitör", "ekran", "display", "televizyon"],
                "reason": "GYK 3(a): 85.28 pozisyonu monitör ve ekranları doğrudan tanımlar; 85.43 genel elektrikli cihazlara tercih edilir."
            },
            {
                "general_heading": "8479",
                "specific_heading": "8471",
                "keywords": ["bilgisayar", "pc", "laptop", "server", "tablet"],
                "reason": "GYK 3(a): 84.71 pozisyonu otomatik bilgi işlem makinelerini özel olarak tanımlar."
            },
            {
                "general_heading": "9031",
                "specific_heading": "9025",
                "keywords": ["termometre", "hidrometre", "nem ölçer"],
                "reason": "GYK 3(a): 90.25 pozisyonu termometreleri özel olarak tanımlar."
            },
            {
                "general_heading": "8504",
                "specific_heading": "8542",
                "keywords": ["pmic", "power management", "entegre", "çip", "chip", "integrated circuit", "ic", "mikroçip", "güç entegre"],
                "reason": "TGTC Fasıl 85 Not 9(b) & GYK 3(a): 85.42 elektronik entegre devreler (PMIC, güç yönetimi vb.), "
                          "işlevleri gereği kapsayabilecek diğer pozisyonlara (85.04 statik konvertörler/transformatörler dahil) göre önceliklidir."
            },
            {
                "general_heading": "8543",
                "specific_heading": "8542",
                "keywords": ["pmic", "entegre", "çip", "chip", "integrated circuit", "ic", "mikroçip", "mikrodenetleyici", "işlemci"],
                "reason": "TGTC Fasıl 85 Not 9(b) & GYK 3(a): 85.42 elektronik entegre devreler, "
                          "85.43 genel elektrikli cihazlar pozisyonuna göre önceliklidir."
            },
            {
                "general_heading": "8517",
                "specific_heading": "8542",
                "keywords": ["entegre", "çip", "chip", "integrated circuit", "ic", "transceiver", "modem çipi", "rf çip", "wi-fi çip"],
                "reason": "TGTC Fasıl 85 Not 9(b) & GYK 3(a): 85.42 elektronik entegre devreler, "
                          "85.17 haberleşme cihazları pozisyonuna göre önceliklidir."
            },
            {
                "general_heading": "8471",
                "specific_heading": "8542",
                "keywords": ["entegre", "çip", "chip", "integrated circuit", "ic", "mikroişlemci", "mikrodenetleyici", "cpu", "gpu"],
                "reason": "TGTC Fasıl 85 Not 9(b) & GYK 3(a): 85.42 elektronik entegre devreler, "
                          "84.71 bilgi işlem makineleri pozisyonuna göre önceliklidir."
            },
            {
                "general_heading": "8504",
                "specific_heading": "8541",
                "keywords": ["diyot", "transistör", "mosfet", "igbt", "tristör", "yarı iletken", "semiconductor"],
                "reason": "TGTC Fasıl 85 Not 9(b) & GYK 3(a): 85.41 yarı iletken tertibat (diyot, transistör, MOSFET), "
                          "85.04 statik konvertörler pozisyonuna göre önceliklidir."
            },
        ]

        heading_codes = [str(h.get("heading") or h.get("gtip_code", "")[:4]).replace(".", "") for h in candidate_headings]

        # TGTC Fasıl 85 Not 9(b) Önceliği: Entegre devreler (85.42) diğer tüm fonksiyonel pozisyonlara göre önceliklidir.
        ic_keywords = ["pmic", "power management", "entegre", "çip", "chip", "integrated circuit", "mikroçip", "güç entegre"]
        if "8542" in heading_codes and any(kw in text_corpus for kw in ic_keywords):
            candidate_8542 = next((h for h in candidate_headings if str(h.get("heading") or h.get("gtip_code", "")[:4]).replace(".", "") == "8542"), None)
            if candidate_8542 and len(heading_codes) > 1:
                applied_rules.append(
                    "TGTC Fasıl 85 Not 9(b) & GYK 3(a): 85.42 elektronik entegre devreler pozisyonu, "
                    "eşyayı işlevine göre kapsayabilecek diğer tüm tarife pozisyonlarına göre öncelik alır."
                )
                return candidate_8542, applied_rules

        # 1. GYK 3(a) Özel Tanım Önceliği
        for rule in SPECIFIC_HEADINGS_MAP:
            gen_h = rule["general_heading"]
            spec_h = rule["specific_heading"]
            if gen_h in heading_codes and spec_h in heading_codes:
                if any(kw in text_corpus for kw in rule["keywords"]):
                    spec_candidate = next((h for h in candidate_headings if str(h.get("heading") or h.get("gtip_code", "")[:4]).replace(".", "") == spec_h), None)
                    if spec_candidate:
                        applied_rules.append(rule["reason"])
                        return spec_candidate, applied_rules

        # 2. GYK 3(b) Esas Nitelik Kuralı
        if features.composition_percentages:
            dominant_material = max(features.composition_percentages.items(), key=lambda x: x[1], default=(None, 0.0))
            if dominant_material[0] and dominant_material[1] >= 0.50:
                applied_rules.append(
                    f"GYK 3(b): Eşyaya esas niteliğini veren '%{int(dominant_material[1]*100)} {dominant_material[0]}' "
                    "bileşeni sınıflandırmada esas alındı."
                )

        # 3. GYK 3(c) Numara Sırasına Göre En Son Pozisyon
        # Eşit derecede geçerli iki veya daha fazla pozisyon varsa, en büyük 4 haneli kod seçilir
        valid_candidates = sorted(
            candidate_headings,
            key=lambda h: str(h.get("heading") or h.get("gtip_code", "")[:4]),
            reverse=True
        )
        if len(valid_candidates) >= 2 and not applied_rules:
            chosen = valid_candidates[0]
            applied_rules.append(
                f"GYK 3(c): Birden fazla pozisyonun eşit derecede geçerli olması sebebiyle "
                f"numara sırasına göre en sonda yer alan {chosen.get('heading') or chosen.get('gtip_code', '')[:4]} pozisyonu seçildi."
            )
            return chosen, applied_rules

        return candidate_headings[0] if candidate_headings else None, applied_rules

    def evaluate_gyk5_packaging(
        self,
        features: ProductFeatures,
        base_heading: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        GYK 5 Ambalaj ve Muhafaza Kontrolü.
        GYK 5(a): Uzun süre kullanılmak üzere eşyaya uygun biçimde yapılmış kutu ve kılıflar
        (örneğin: kulaklık şarj kutusu, kamera kılıfı, müzik aleti kutusu) eşya ile birlikte
        sunulduğunda o eşyanın tarifesine dahil edilir.
        """
        packaging_text = (
            f"{features.product_name} {getattr(features, 'accessories_or_packaging', '') or ''} "
            f"{features.intended_use or ''}"
        ).lower()

        fitted_cases_keywords = [
            "taşıma kutu", "şarj kutu", "taşıma kılıf", "özel kılıf", "muhafaza kutu",
            "kulaklık kutu", "kamera çanta", "alet çanta", "hardcase", "carrying case"
        ]

        if any(kw in packaging_text for kw in fitted_cases_keywords):
            justification = (
                f"GYK 5(a): Eşya ile birlikte sunulan ve uzun süreli kullanıma uygun özel şekillendirilmiş "
                f"taşıma/muhafaza kutusu, eşyanın esas tarifesi ({base_heading}) kapsamında birlikte sınıflandırılmıştır."
            )
            return True, justification

        return False, None


rule_engine = RuleEngine()
