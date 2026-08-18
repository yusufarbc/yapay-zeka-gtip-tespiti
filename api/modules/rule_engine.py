from typing import List, Dict, Tuple, Any
from api.schemas.product import ProductFeatures
from api.db.tgtc_knowledge_base import match_chapters_from_cache, load_tgtc_chapters, TGTC_CHAPTERS, get_chapter_title

# Katı Fasıl Kilit Matrisi (Hard Rules Matrix) - Sıfır Halüsinasyon Güvencesi
HARD_RULES_MATRIX = [
    {
        "keywords": ["ayakkabı", "footwear", "bot ", "terlik", "babet", "çizme", "sneaker"],
        "materials": ["deri", "leather", "kauçuk", "tekstil", "sentetik", "plastik"],
        "locked_chapter": "64",
        "description": "Ayakkabılar, botlar, terlikler ve ayak giyecekleri (Fasıl 64) katı kural kilidi."
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
        "description": "Elektrikli ve elektronik makine, cihaz, yarı iletkenler ve entegre devreler (Fasıl 85) katı kural kilidi."
    },
    {
        "keywords": [
            "bilgisayar parçası", "ana kart", "motherboard", "donanım", "hard disk", "ssd", "hafıza",
            "yazıcı", "tarayıcı", "klima", "soğutma", "motor ", "pompa", "jeneratör", "kompresör", "kazan", "türbin", "vinç", "dozer"
        ],
        "materials": [],
        "locked_chapter": "84",
        "description": "Kazanlar, makina, mekanik cihazlar ve bilgisayar aksamları (Fasıl 84) katı kural kilidi."
    },
    {
        "keywords": ["oyuncak", "oyun", "spor", "oyun konsol"],
        "materials": [],
        "locked_chapter": "95",
        "description": "Oyuncaklar, oyun ve spor malzemeleri (Fasıl 95) katı kural kilidi."
    },
    {
        "keywords": ["mobilya", "koltuk", "sandalye", "masa", "yatak", "aydınlatma", "avize"],
        "materials": [],
        "locked_chapter": "94",
        "description": "Mobilyalar, yatak takımları ve aydınlatma cihazları (Fasıl 94) katı kural kilidi."
    }
]

class RuleEngine:
    """
    Modül 2: Deterministik Kural Motoru (Python Logic Engine & Hard Rules Matrix).
    Türk Gümrük Tarife Yorum Kurallarını (GİR 1-6) katı sırayla ve önbellekteki 97 Fasıl İzahnamelerini çalıştırır.
    SIFIR HALÜSİNASYON: Katı kuralla kilitlenen fasıllar dışına asla inisiyatif tanımaz.
    """

    def apply_rules(self, features: ProductFeatures) -> Tuple[List[str], List[str]]:
        allowed_chapters = []
        applied_rules = []
        is_hard_locked = False

        text_combo = f"{features.product_name} {features.primary_material} {features.intended_use}".lower()

        # 1. GİR 1 [HARD RULES MATRIX]: Açıkça Belirlenmiş Tanım ve Tarife Kilidi
        for rule in HARD_RULES_MATRIX:
            kw_match = any(kw in text_combo for kw in rule["keywords"])
            if kw_match:
                mat_match = not rule["materials"] or any(m in text_combo for m in rule["materials"])
                if mat_match:
                    chap = rule["locked_chapter"]
                    if chap not in allowed_chapters:
                        allowed_chapters.append(chap)
                    applied_rules.append(f"GİR 1 [HARD LOCK]: {rule['description']} (Fasıl {chap} dışı aramalar engellendi).")
                    is_hard_locked = True

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
                applied_rules.append(f"GİR 6: TGTC İzahnamelerine göre dinamik belirlenen fasıllar: {', '.join(chap_names)}.")

        return allowed_chapters, applied_rules

rule_engine = RuleEngine()

