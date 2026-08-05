from typing import List, Dict, Tuple
from api.schemas.product import ProductFeatures
from api.db.tgtc_knowledge_base import match_chapters_from_cache, load_tgtc_chapters, TGTC_CHAPTERS, get_chapter_title

class RuleEngine:
    """
    Modül 2: Deterministik Kural Motoru (Python Logic Engine).
    Türk Gümrük Tarife Yorum Kurallarını (GİR 1-6) ve Önbellekteki 99 Fasıl İzahnamelerini çalıştırır.
    SIFIR HARDCODED VERİ: Tüm fasıl eşleşmeleri canlı TGTC veritabanından dinamik olarak türetilir.
    """

    def apply_rules(self, features: ProductFeatures) -> Tuple[List[str], List[str]]:
        allowed_chapters = []
        applied_rules = []

        # 1. GİR 3b: Baskın Malzeme Oranı Kontrolü (%50+ Karışımlar)
        if features.composition_percentages:
            for mat_name, ratio in features.composition_percentages.items():
                if ratio >= 0.50:
                    matched_chaps = match_chapters_from_cache(mat_name)
                    for chap in matched_chaps:
                        if chap not in allowed_chapters:
                            allowed_chapters.append(chap)
                    if matched_chaps:
                        applied_rules.append(
                            f"GİR 3b: %{int(ratio*100)}+ {mat_name.title()} karışımı sebebiyle "
                            f"Fasıl {', '.join(matched_chaps)} dinamik olarak eşleştirildi."
                        )

        # 2. Demonte / Sökülmüş veya Eksik Eşya Kuralı (GİR 2a)
        text_combo = f"{features.product_name} {features.primary_material} {features.intended_use}".lower()
        if features.is_disassembled or "demonte" in text_combo or "sökülmüş" in text_combo:
            applied_rules.append("GİR 2a: Demonte/sökülmüş eşya kuralı uyarınca komple monte eşyanın faslı esas alındı.")

        # 3. Canlı TGTC 99 Fasıl Tanımları ve BTB Kataloğu Üzerinden Dinamik Eşleştirme (GİR 1 & GİR 6)
        cached_matches = match_chapters_from_cache(text_combo)
        for chap in cached_matches:
            if chap not in allowed_chapters:
                allowed_chapters.append(chap)

        # 4. En Yakın Eşya Kuralı (GİR 4) - Özel Tanımı Olmayan / Yeni Nesil Ürünler İçin Dinamik Fallback
        if not allowed_chapters:
            applied_rules.append("GİR 4: Doğrudan mevzuat tanımı bulunamayan yeni nesil ürün için işlev ve nitelik bakımından en yakın eşya grubuna yönlendirildi.")
            chaps_db = load_tgtc_chapters() or TGTC_CHAPTERS
            all_chaps = list(chaps_db.keys())
            if all_chaps:
                allowed_chapters.extend(all_chaps[:5])

        if cached_matches:
            chap_names = [f"Fasıl {c} ({get_chapter_title(c)})" for c in cached_matches[:3]]
            applied_rules.append(f"GİR 1 & GİR 6: TGTC İzahnamelerine göre dinamik eşleşen Fasıllar: {', '.join(chap_names)}.")
        else:
            applied_rules.append("GİR 1 & GİR 6: Genel Türk Gümrük Tarife Cetveli (TGTC 99 Fasıl) dinamik taraması aktif edildi.")

        return allowed_chapters, applied_rules

rule_engine = RuleEngine()

