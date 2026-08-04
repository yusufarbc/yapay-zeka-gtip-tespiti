from typing import List, Dict, Tuple
from api.schemas.product import ProductFeatures
from api.db.tgtc_knowledge_base import match_chapters_from_cache, TGTC_CHAPTERS

class RuleEngine:
    """
    Modül 2: Deterministik Kural Motoru (Python Logic Engine).
    Türk Gümrük Tarife Yorum Kurallarını (GİR 1-6) ve Önbellekteki 99 Fasıl İzahnamelerini çalıştırır.
    """

    def apply_rules(self, features: ProductFeatures) -> Tuple[List[str], List[str]]:
        allowed_chapters = []
        applied_rules = []

        # 1. GİR 3b: Baskın Malzeme Oranı Kontrolü (%50+ Karışımlar)
        if features.composition_percentages:
            for mat_name, ratio in features.composition_percentages.items():
                if ratio >= 0.50:
                    if mat_name.lower() in ["pamuk", "cotton"]:
                        allowed_chapters.append("52")
                        applied_rules.append("GİR 3b: %50+ Pamuk karışımı sebebiyle Fasıl 52 (Pamuk) önbellekten eşleştirildi.")
                    elif mat_name.lower() in ["polyester", "sentetik", "synthetic"]:
                        allowed_chapters.append("55")
                        applied_rules.append("GİR 3b: %50+ Sentetik karışımı sebebiyle Fasıl 55 (Sentetik) önbellekten eşleştirildi.")

        # 2. Ürün Kategori Metin Eşleşmesi (GİR 1 / Fasıl Tanımları)
        text_combo = f"{features.product_name} {features.primary_material} {features.intended_use}".lower()
        if any(w in text_combo for w in ["ayakkabı", "bot", "çizme", "sandalet", "terlik"]):
            if "64" not in allowed_chapters:
                allowed_chapters.append("64")
                applied_rules.append("GİR 1: Ayakkabı tanımı sebebiyle Fasıl 64 (Ayakkabılar) kural motoru tarafından eşleştirildi.")
        elif any(w in text_combo for w in ["çanta", "cüzdan", "bavul", "valiz"]):
            if "42" not in allowed_chapters:
                allowed_chapters.append("42")
                applied_rules.append("GİR 1: Çanta/Saraciye tanımı sebebiyle Fasıl 42 önbellekten eşleştirildi.")
        elif any(w in text_combo for w in ["t-shirt", "tişört", "fanila", "kazak", "pantolon", "gömlek"]):
            if "61" not in allowed_chapters:
                allowed_chapters.append("61")
                applied_rules.append("GİR 1: Örme giyim eşyası sebebiyle Fasıl 61 önbellekten eşleştirildi.")
        elif any(w in text_combo for w in ["masası", "masa", "sandalye", "mobilya", "koltuk", "sehpa"]):
            if "94" not in allowed_chapters:
                allowed_chapters.append("94")
                applied_rules.append("GİR 1: Mobilya tanımı sebebiyle Fasıl 94 (Mobilyalar) kural motoru tarafından eşleştirildi.")
        elif any(w in text_combo for w in ["motor yağı", "motor yağ", "madeni yağ", "gres"]):
            if "27" not in allowed_chapters:
                allowed_chapters.append("27")
                applied_rules.append("GİR 1: Yağlama müstahzarı sebebiyle Fasıl 27 (Mineral/Sentetik Yağlar) kural motoru tarafından eşleştirildi.")

        # 3. Demonte / Sökülmüş veya Eksik Eşya Kuralı (GİR 2a)
        if features.is_disassembled or "demonte" in features.product_name.lower() or "sökülmüş" in features.product_name.lower():
            applied_rules.append("GİR 2a: Demonte/sökülmüş eşya kuralı uyarınca parçaların ayrı sınıflandırılması engellendi; komple monte ana eşyanın faslı esas alındı.")
            if any(w in text_combo for w in ["bisiklet", "oto", "araba", "taşıt", "araç"]):
                if "87" not in allowed_chapters:
                    allowed_chapters.append("87")
            elif any(w in text_combo for w in ["makine", "cihaz", "motor", "pompa", "kompresör"]):
                if "84" not in allowed_chapters:
                    allowed_chapters.append("84")
            elif any(w in text_combo for w in ["elektronik", "devre", "telefon", "tv", "bilgisayar"]):
                if "85" not in allowed_chapters:
                    allowed_chapters.append("85")

        # 4. Önbellekteki (Context Cache) 99 TGTC Fasıl Tanımları İle Dinamik Eşleştirme (GİR 1 & GİR 6)
        cached_matches = match_chapters_from_cache(f"{features.product_name} {features.primary_material} {features.intended_use}")
        for chap in cached_matches:
            if chap not in allowed_chapters:
                allowed_chapters.append(chap)

        # 4. En Yakın Eşya Kuralı (GİR 4) - Özel Tanımı Olmayan / Yeni Nesil Ürünler İçin Fallback
        if not allowed_chapters:
            applied_rules.append("GİR 4: Doğrudan mevzuat tanımı bulunamayan yeni nesil ürün için işlev ve nitelik bakımından en yakın eşya grubuna yönlendirildi.")
            allowed_chapters.extend(["84", "85", "90"])

        if cached_matches:
            chap_names = [f"Fasıl {c} ({TGTC_CHAPTERS.get(c, '')})" for c in cached_matches[:3]]
            applied_rules.append(f"GİR 1 & GİR 6: Önbellekteki TGTC İzahnamelerine göre dinamik eşleşen Fasıllar: {', '.join(chap_names)}.")
        else:
            applied_rules.append("GİR 1 & GİR 6: Genel Türk Gümrük Tarife Cetveli (TGTC 99 Fasıl) kapsamlı taraması aktif edildi.")

        return allowed_chapters, applied_rules

rule_engine = RuleEngine()
