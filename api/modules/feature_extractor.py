import json
import re
import os
import logging
from typing import Any, Dict, Optional, Tuple
from api.schemas.product import ProductFeatures
from api.config import settings

logger = logging.getLogger("FeatureExtractor")


# Kısa ürün tanımlarında yalnız kullanıcının açıkça yazdığı malzemeyi çıkarır.
# Bu sözlük sınıflandırma kararı vermez; LLM'nin "ahşap sandalye" gibi açık
# bir girdiyi yeniden yorumlayıp gecikme ve örtük varsayım üretmesini önler.
_EXPLICIT_MATERIALS = {
    "ahşap": ("ahşap", "ahsap", "wood", "wooden"),
    "plastik": ("plastik", "plastic"),
    "çelik": ("çelik", "celik", "steel"),
    "demir": ("demir", "iron"),
    "alüminyum": ("alüminyum", "aluminyum", "alimunyum", "aliminyum", "aluminium", "aluminum"),
    "cam": ("cam", "glass"),
    "kauçuk": ("kauçuk", "kaucuk", "rubber"),
    "deri": ("deri", "leather"),
    "pamuk": ("pamuk", "cotton"),
    "yün": ("yün", "yun", "wool"),
    "polyester": ("polyester",),
    "seramik": ("seramik", "ceramic"),
    "bakır": ("bakır", "bakir", "copper"),
}

_DOCUMENT_MARKERS = (
    "fatura no", "invoice", "packing list", "proforma", "kalem no",
    "model no", "stok kodu", "ürün kodu", "product code",
)



def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE) is not None

def regex_specs(text_lower: str) -> Tuple[Dict[str, str], Optional[Dict[str, float]]]:
    """Metindeki açık teknik ölçüler (voltaj, güç, ağırlık) ve pamuk/polyester oranı."""
    specs = {}
    # Teknik parametre tespiti: Voltaj, Güç, Ağırlık, Frekans
    volt_match = re.search(r'(\d+)\s*(?:v|volt)', text_lower)
    if volt_match:
        specs["voltage"] = f"{volt_match.group(1)}V"

    watt_match = re.search(r'(\d+)\s*(?:w|watt)', text_lower)
    if watt_match:
        specs["power"] = f"{watt_match.group(1)}W"

    weight_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:kg|kilo|gr|gram)', text_lower)
    if weight_match:
        specs["weight"] = weight_match.group(0)

    # Karışım tespiti
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
    return specs, composition


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

    def _extract_explicit_material(self, text_lower: str) -> str:
        matches = [
            canonical
            for canonical, aliases in _EXPLICIT_MATERIALS.items()
            if any(_contains_term(text_lower, alias) for alias in aliases)
        ]
        return " / ".join(dict.fromkeys(matches)) if matches else "Belirtilmedi"

    def _is_simple_explicit_description(self, raw_text: str, image_uri: str = None) -> bool:
        """Tek ürünlük kısa tanımı belge/teknik veri metninden ayırır."""
        if image_uri:
            return False
        normalized = " ".join(str(raw_text or "").split())
        if not normalized or len(normalized) > 240:
            return False
        if len(re.findall(r"[0-9a-zA-ZçğıöşüÇĞİÖŞÜ]+", normalized)) > 24:
            return False
        lowered = normalized.lower()
        if any(marker in lowered for marker in _DOCUMENT_MARKERS):
            return False
        # Uzun teknik değer kümeleri veya tablo benzeri girdiler yapılandırılmış
        # çıkarıcıya bırakılır. Tek bir ölçü/değer kısa yolu engellemez.
        if str(raw_text).count("\n") > 1 or normalized.count(":") > 2:
            return False
        return True

    def _build_explicit_features(
        self,
        raw_text: str,
        text_lower: str,
        specs: Dict[str, str],
        composition: Any,
    ) -> ProductFeatures:
        normalized = " ".join(raw_text.split())
        accessories = None
        for acc_term in ("taşıma kutulu", "şarj kutulu", "özel kılıflı", "kutulu", "kılıflı", "taşıma kutusu", "şarj kutusu", "özel kılıf"):
            if acc_term in text_lower:
                accessories = acc_term
                break

        return ProductFeatures(
            product_name=normalized[:2000],
            commercial_name=normalized[:500],
            primary_material=self._extract_explicit_material(text_lower),
            function=normalized[:1000],
            accessories_or_packaging=accessories,
            composition_percentages=composition,
            intended_use=normalized[:1000],
            is_set_or_kit=any(_contains_term(text_lower, w) for w in ("set", "takım", "kit")),
            is_disassembled=any(
                _contains_term(text_lower, w) for w in ("demonte", "sökülmüş", "parça halinde")
            ),
            technical_specifications=specs
        )

    def extract_features(self, raw_text: str, image_uri: str = None) -> ProductFeatures:
        text_lower = str(raw_text or "").lower()
        specs, composition = regex_specs(text_lower)

        # Açık ve kısa ürün tanımında deterministik hızlı yol
        if self._is_simple_explicit_description(raw_text, image_uri):
            logger.info("Deterministik özellik çıkarımı kullanıldı (kısa açık ürün tanımı).")
            return self._build_explicit_features(raw_text, text_lower, specs, composition)

        try:
            from api.modules.vertex_client import get_genai_client
            from google.genai import types
            client = get_genai_client()
            prompt = (
                f"Aşağıdaki gümrük ürün açıklamasını veya fatura metnini analiz et.\n"
                f"Metin: {raw_text}\n\n"
                f"Lütfen sadece geçerli bir JSON yanıtı döndür:\n"
                f"{{\n"
                f'  "product_name": "ürünün ticari adı",\n'
                f'  "commercial_name": "marka/model veya ticari adı",\n'
                f'  "primary_material": "baskın malzeme",\n'
                f'  "function": "işlev/temel fonksiyon (örn. ses dinleme, kablosuz iletişim)",\n'
                f'  "accessories_or_packaging": "birlikte verilen ambalaj/kutu (örn. taşıma kutusu, şarj kablosu)",\n'
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
                    temperature=0.0,
                    max_output_tokens=1024,
                    response_mime_type="application/json",
                )
            except Exception:
                config = None

            response = client.models.generate_content(
                model=settings.EXTRACTOR_LLM_MODEL,
                contents=prompt,
                config=config,
            )

            if response.text:
                match = re.search(r'\{.*\}', response.text, re.DOTALL)
                clean_json = match.group(0) if match else re.sub(r'```json\s*|\s*```', '', response.text).strip()
                data = json.loads(clean_json)
                llm_specs = data.get("technical_specifications", {})
                if not isinstance(llm_specs, dict):
                    llm_specs = {}
                llm_specs = {
                    str(key)[:100]: str(value)[:500]
                    for key, value in llm_specs.items()
                    if key is not None and value is not None
                }
                llm_specs.update(specs)
                return ProductFeatures(
                    product_name=data.get("product_name", raw_text[:70]),
                    commercial_name=data.get("commercial_name", raw_text[:70]),
                    primary_material=data.get("primary_material", self._extract_material_dynamically(text_lower)),
                    function=data.get("function", raw_text[:100]),
                    accessories_or_packaging=data.get("accessories_or_packaging"),
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
