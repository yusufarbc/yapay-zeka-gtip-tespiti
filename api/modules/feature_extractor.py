import re
import json
from typing import Dict, Any
from api.schemas.product import ProductFeatures
from api.config import settings

class FeatureExtractor:
    """
    Modül 1: Multimodal Özellik Çıkarıcı.
    Metin ve görsel içerikten teknik ürün parametrelerini (Pydantic ProductFeatures) çıkarır.
    GTİP tahmini YAPMAZ.
    """

    def extract_features(self, raw_text: str, image_uri: str = None) -> ProductFeatures:
        text_lower = raw_text.lower()
        
        # Malzeme tespiti
        primary_material = "Belirtilmedi"
        composition = {}

        if "pamuk" in text_lower or "cotton" in text_lower:
            primary_material = "Pamuk"
            # Karışım arama
            cotton_match = re.search(r'%?\s*(\d{2})\s*(?:pamuk|cotton)', text_lower)
            poly_match = re.search(r'%?\s*(\d{2})\s*(?:polyester|sentetik)', text_lower)
            if cotton_match:
                c_val = float(cotton_match.group(1)) / 100.0
                p_val = float(poly_match.group(1))/100.0 if poly_match else (1.0 - c_val)
                composition = {"cotton": c_val, "polyester": p_val}
            else:
                composition = {"cotton": 1.0}
        elif "plastik" in text_lower or "plastic" in text_lower:
            primary_material = "Plastik"
        elif "çelik" in text_lower or "metal" in text_lower or "steel" in text_lower:
            primary_material = "Çelik / Metal"

        # Kullanım amacı tespiti
        intended_use = "Genel Kullanım"
        if "oyuncak" in text_lower or "toy" in text_lower or "çocuk" in text_lower:
            intended_use = "Oyuncak / Çocuk"
        elif "diş" in text_lower or "fırça" in text_lower or "ağız" in text_lower or "kişisel bakım" in text_lower:
            intended_use = "Kişisel Bakım / Ağız Sağlığı"
        elif "bilgisayar" in text_lower or "laptop" in text_lower or "notebook" in text_lower:
            intended_use = "Bilgi İşlem / Elektronik"
        elif "bisiklet" in text_lower or "bike" in text_lower:
            intended_use = "Ulaşım / Spor"

        # Demonte / Set durumu
        is_set = "set" in text_lower or "takım" in text_lower or "kit" in text_lower
        is_disassembled = "demonte" in text_lower or "sökülmüş" in text_lower or "parça halinde" in text_lower

        # Teknik özellikler
        specs = {}
        if "şarj" in text_lower or "pil" in text_lower or "batarya" in text_lower:
            specs["power_source"] = "Şarj Edilebilir / Bataryalı"
        if "motor" in text_lower or "elektrik motoru" in text_lower:
            specs["has_electric_motor"] = "true"
        
        weight_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:gr|gram|kg)', text_lower)
        if weight_match:
            specs["weight"] = weight_match.group(0)

        # Ürün adı türetme
        first_line = raw_text.strip().split("\n")[0]
        product_name = first_line[:60] if len(first_line) > 5 else "Tanımlanmamış Ürün"

        return ProductFeatures(
            product_name=product_name,
            primary_material=primary_material,
            composition_percentages=composition if composition else None,
            intended_use=intended_use,
            is_set_or_kit=is_set,
            is_disassembled=is_disassembled,
            technical_specifications=specs
        )

feature_extractor = FeatureExtractor()
