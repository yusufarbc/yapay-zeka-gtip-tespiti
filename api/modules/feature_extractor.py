import json
import re
import os
from typing import Dict, Any
from api.schemas.product import ProductFeatures
from api.config import settings

class FeatureExtractor:
    """
    Modül 1: Multimodal & Dynamic Feature Extractor (LLM-Driven & Dynamic Material Extraction).
    Her türlü ürün metninden veya faturadan sıfır hardcoded şablon bağımlılığı ile 
    tüm teknik parametreleri ve hammadde niteliklerini dinamik olarak çıkarır.
    """

    def _extract_material_dynamically(self, text_lower: str) -> str:
        materials = [
            ("pamuk", "Pamuk / Tekstil"), ("polyester", "Sentetik / Polyester"), ("deri", "Hakiki / Suni Deri"),
            ("ahşap", "Ahşap / Tahta"), ("plastik", "Plastik / Polimer"), ("cam", "Cam"),
            ("çelik", "Paslanmaz Çelik"), ("demir", "Demir / Çelik"), ("alüminyum", "Alüminyum"),
            ("kauçuk", "Kauçuk / Lastik"), ("bakır", "Bakır"), ("kağıt", "Kağıt / Selüloz"),
            ("ipek", "İpek"), ("yün", "Yün"), ("altın", "Altın / Değerli Metal"),
            ("gümüş", "Gümüş"), ("seramik", "Seramik / Porselen"), ("titanyum", "Titanyum"),
            ("entegre", "Yarı İletken / Entegre Devre (IC)"), ("pdip", "Yarı İletken PDIP Kılıfı"),
            ("çip", "Yarı İletken Çip"), ("cip", "Yarı İletken Çip"), ("yarı iletken", "Yarı İletken Silisyum"),
            ("yari iletken", "Yarı İletken Silisyum"), ("transistör", "Yarı İletken Transistör"),
            ("diyot", "Yarı İletken Diyot"), ("mikroişlemci", "Mikroişlemci / Entegre Devre"),
            ("zeytinyağ", "Zeytinyağı"), ("kahve", "Kahve Çekirdeği"), ("parfüm", "Kozmetik / Parfüm"),
            ("ilaç", "Eczacılık Müstahzarı"), ("yağ", "Mineral / Sentetik Yağ"), ("lastik", "Kauçuk Lastik"),
            ("akıllı telefon", "Elektronik / Akıllı Telefon"), ("bilgisayar", "Elektronik / Bilgisayar"),
            ("televizyon", "Elektronik / TV"), ("diş fırça", "Elektrikli Ev Aleti"), ("bisiklet", "Taşıt / Bisiklet")
        ]
        found = []
        for kw, label in materials:
            if kw in text_lower:
                found.append(label)
        if found:
            return " / ".join(found[:2])
        return "Genel Sanayi ve Ticaret Eşyası"

    def extract_features(self, raw_text: str, image_uri: str = None) -> ProductFeatures:
        text_lower = raw_text.lower()
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        
        # Temel teknik nitelik tespiti
        specs = {}
        if "motor" in text_lower:
            specs["has_electric_motor"] = "true"
        if "şarj" in text_lower or "batarya" in text_lower or "5g" in text_lower or "pil" in text_lower:
            specs["power_source"] = "Bataryalı / Şarjlı"

        composition = None
        if "pamuk" in text_lower or "cotton" in text_lower:
            cotton_match = re.search(r'%?\s*(\d{2})\s*(?:pamuk|cotton)', text_lower)
            poly_match = re.search(r'%?\s*(\d{2})\s*(?:polyester|sentetik)', text_lower)
            if cotton_match:
                c_val = float(cotton_match.group(1)) / 100.0
                p_val = float(poly_match.group(1))/100.0 if poly_match else (1.0 - c_val)
                composition = {"cotton": c_val, "polyester": p_val}
            else:
                composition = {"cotton": 1.0}

        if api_key:
            try:
                from google import genai
                from api.modules.context_cache_manager import context_cache_manager
                client = genai.Client(api_key=api_key)
                prompt = (
                    f"Aşağıdaki gümrük ürün açıklamasını veya fatura metnini analiz et.\n"
                    f"Metin: {raw_text}\n\n"
                    f"Lütfen sadece geçerli bir JSON yanıtı döndür:\n"
                    f"{{\n"
                    f'  "product_name": "ürünün ticari adı",\n'
                    f'  "primary_material": "baskın malzeme",\n'
                    f'  "intended_use": "kullanım amacı",\n'
                    f'  "is_set_or_kit": false,\n'
                    f'  "is_disassembled": false,\n'
                    f'  "technical_specifications": {{"özellik": "değer"}}\n'
                    f"}}\n"
                )
                cached_config = context_cache_manager.get_cached_config(settings.EXTRACTOR_LLM_MODEL)
                if cached_config:
                    response = client.models.generate_content(
                        model=settings.EXTRACTOR_LLM_MODEL,
                        contents=prompt,
                        config=cached_config
                    )
                else:
                    response = client.models.generate_content(
                        model=settings.EXTRACTOR_LLM_MODEL,
                        contents=prompt
                    )
                if response.text:
                    match = re.search(r'\{.*\}', response.text, re.DOTALL)
                    clean_json = match.group(0) if match else re.sub(r'```json\s*|\s*```', '', response.text).strip()
                    data = json.loads(clean_json)
                    llm_specs = data.get("technical_specifications", {})
                    llm_specs.update(specs)
                    return ProductFeatures(
                        product_name=data.get("product_name", raw_text[:70]),
                        primary_material=data.get("primary_material", self._extract_material_dynamically(text_lower)),
                        composition_percentages=composition,
                        intended_use=data.get("intended_use", "Genel Kullanım"),
                        is_set_or_kit=data.get("is_set_or_kit", False),
                        is_disassembled=data.get("is_disassembled", False),
                        technical_specifications=llm_specs
                    )
            except Exception as e:
                import logging
                logging.getLogger("FeatureExtractor").warning(f"LLM Feature extraction uyarısı: {e}")

        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        product_name = lines[0][:80] if lines else "Analiz Edilen Ürün"
        
        is_set = any(w in text_lower for w in ["set", "takım", "kit"])
        is_disassembled = any(w in text_lower for w in ["demonte", "sökülmüş", "parça"])
        dynamic_material = self._extract_material_dynamically(text_lower)

        return ProductFeatures(
            product_name=product_name,
            primary_material=dynamic_material,
            composition_percentages=composition,
            intended_use=raw_text[:60],
            is_set_or_kit=is_set,
            is_disassembled=is_disassembled,
            technical_specifications=specs
        )

feature_extractor = FeatureExtractor()
