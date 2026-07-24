from typing import List, Dict, Tuple
from api.schemas.product import ProductFeatures

class RuleEngine:
    """
    Modül 2: Deterministik Kural Motoru (Python Logic Engine).
    Türk Gümrük Tarife Yorum Kurallarını (GİR) çalıştırır.
    """

    def apply_rules(self, features: ProductFeatures) -> Tuple[List[str], List[str]]:
        """
        Gümrük kurallarını çalıştırarak onaylanan Fasılları (allowed_chapters)
        ve uygulanan GİR kurallarını (applied_rules) döndürür.
        """
        allowed_chapters = []
        applied_rules = []

        # 1. GİR 3b: Baskın Malzeme Kuralı (Composition %50+)
        if features.composition_percentages:
            for mat_name, ratio in features.composition_percentages.items():
                if ratio >= 0.50:
                    if mat_name.lower() in ["pamuk", "cotton"]:
                        allowed_chapters.append("52") # Fasıl 52: Pamuk
                        applied_rules.append("GİR 3b: %50+ Pamuk karışımı sebebiyle Fasıl 52 baskın kılındı, Fasıl 55 elendi.")
                    elif mat_name.lower() in ["polyester", "sentetik", "synthetic"]:
                        allowed_chapters.append("55") # Fasıl 55: Sentetik
                        applied_rules.append("GİR 3b: %50+ Sentetik karışımı sebebiyle Fasıl 55 baskın kılındı.")

        # 2. Yasaklı Fasıl Matrisi (Hard Exclusion Matrix)
        if "oyuncak" in features.intended_use.lower():
            allowed_chapters = ["95"] # Zorunlu Fasıl 95 (Oyuncaklar)
            applied_rules.append("Yasaklı Fasıl Matrisi: Oyuncak kullanım amacı sebebiyle Fasıl 39 (Plastik) elendi, Fasıl 95 zorunlu tutuldu.")
        
        # 3. Demonte / Sökülmüş Aksam Kuralı (GİR 2a)
        if features.is_disassembled:
            applied_rules.append("GİR 2a: Demonte eşya kuralı uyarınca aksamların bağımsız GTİP alması engellendi, monte ana ürün Fasılları zorunlu tutuldu.")

        # 4. Genel Elektrikli / Bilgi İşlem / Alet Kriterleri
        if not allowed_chapters:
            use_lower = features.intended_use.lower()
            mat_lower = features.primary_material.lower()

            if "kişisel bakım" in use_lower or features.technical_specifications.get("has_electric_motor") == "true":
                allowed_chapters.append("85") # Fasıl 85: Elektrikli Ev Aletleri
                applied_rules.append("GİR 1: Elektrik motorlu cihaz tanımı uyarınca Fasıl 85 aktif edildi.")
            elif "bilgi işlem" in use_lower or "elektronik" in use_lower:
                allowed_chapters.append("84") # Fasıl 84: Otomatik Bilgi İşleme Cihazları
                applied_rules.append("GİR 1: Otomatik bilgi işleme makineleri pozisyonu uyarınca Fasıl 84 aktif edildi.")
            elif "ulaşım" in use_lower or "bisiklet" in use_lower:
                allowed_chapters.append("87") # Fasıl 87: Kara Taşıtları
                applied_rules.append("GİR 1: Taşıtlar ve aksamları uyarınca Fasıl 87 aktif edildi.")
            elif "plastik" in mat_lower:
                allowed_chapters.append("39") # Fasıl 39: Plastikler
                applied_rules.append("GİR 1: Plastik hammadde pozisyonu uyarınca Fasıl 39 aktif edildi.")
            else:
                # Varsayılan geniş tarama
                allowed_chapters = ["39", "52", "55", "84", "85", "87", "95"]

        return allowed_chapters, applied_rules

rule_engine = RuleEngine()
