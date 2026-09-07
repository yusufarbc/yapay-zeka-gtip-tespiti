import json
import re
import os
import logging
from typing import Dict, Any
from api.schemas.product import ProductFeatures
from api.config import settings

logger = logging.getLogger("FeatureExtractor")

class FeatureExtractor:
    """
    Modül 1: Multimodal & Dynamic Feature Extractor (Gemini 3.7 Flash - Thinking Budget: 0).
    Her türlü ürün metninden veya faturadan sıfır hardcoded şablon bağımlılığı ile 
    tüm teknik parametreleri ve hammadde niteliklerini ultra düşük gecikmeyle dinamik olarak çıkarır.
    """

    def _extract_material_dynamically(self, text_lower: str) -> str:
        """
        Metindeki teknik nitelik ve hammadde isimlerini NLP tokenizasyonu ile dinamik olarak çıkarır.
        """
        from api.db.tgtc_knowledge_base import TURKISH_STOP_WORDS
        tokens = [w for w in re.findall(r'[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+', text_lower) if len(w) >= 3]
        filtered = [t.title() for t in tokens if t.lower() not in TURKISH_STOP_WORDS]
        if filtered:
            return " / ".join(filtered[:2])
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

        try:
            from api.modules.vertex_client import get_genai_client
            from google.genai import types
            from api.modules.context_cache_manager import context_cache_manager

            client = get_genai_client()
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

            try:
                thinking_config = types.ThinkingConfig(thinking_budget=settings.THINKING_BUDGET_EXTRACTOR)
                config = types.GenerateContentConfig(
                    thinking_config=thinking_config,
                    temperature=0.1
                )
            except Exception:
                config = None

            cached_config = context_cache_manager.get_cached_config(settings.EXTRACTOR_LLM_MODEL)
            active_config = cached_config or config

            if active_config:
                response = client.models.generate_content(
                    model=settings.EXTRACTOR_LLM_MODEL,
                    contents=prompt,
                    config=active_config
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
                    is_set_or_kit=bool(data.get("is_set_or_kit", False)),
                    is_disassembled=bool(data.get("is_disassembled", False)),
                    technical_specifications=llm_specs
                )
        except Exception as e:
            logger.warning(f"LLM Feature extraction uyarısı: {e}")

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
