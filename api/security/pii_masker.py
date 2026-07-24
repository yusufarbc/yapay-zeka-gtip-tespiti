import re
from typing import Dict, Tuple

class PIIMasker:
    """
    KVKK Regülasyon Uyum Modülü.
    LLM (Gemini) API'sine istek atılmadan önce metin içerisindeki hassas kişisel 
    ve kurumsal verileri (TCKN, VKN, Telefon, E-posta, Adres) maskeler.
    """
    
    def __init__(self):
        # Regex kalıpları
        self.tckn_pattern = r'\b[1-9]\d{10}\b'
        self.vkn_pattern = r'\b\d{10}\b'
        self.email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        self.phone_pattern = r'(\+?90|0)?[ -]?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}'

    def mask_text(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Metin içindeki kişisel verileri maskeler ve geri yükleme haritası (mapping) döndürür.
        """
        if not text:
            return "", {}

        mapping = {}
        masked_text = text

        # 1. E-posta Maskeleme
        emails = re.findall(self.email_pattern, masked_text)
        for idx, email in enumerate(emails):
            placeholder = f"[MASKED_EMAIL_{idx+1}]"
            mapping[placeholder] = email
            masked_text = masked_text.replace(email, placeholder)

        # 2. Telefon Maskeleme
        phones = re.findall(self.phone_pattern, masked_text)
        for idx, phone_tuple in enumerate(phones):
            # regex findall grupları için tam eşleşmeyi bul
            full_match = phone_tuple[0] if isinstance(phone_tuple, tuple) else phone_tuple
            if full_match:
                placeholder = f"[MASKED_PHONE_{idx+1}]"
                mapping[placeholder] = full_match
                masked_text = masked_text.replace(full_match, placeholder)

        # 3. TCKN Maskeleme (11 Haneli Rakam)
        tckns = re.findall(self.tckn_pattern, masked_text)
        for idx, tckn in enumerate(tckns):
            placeholder = f"[MASKED_TCKN_{idx+1}]"
            mapping[placeholder] = tckn
            masked_text = masked_text.replace(tckn, placeholder)

        # 4. VKN Maskeleme (10 Haneli Rakam)
        vkns = re.findall(self.vkn_pattern, masked_text)
        for idx, vkn in enumerate(vkns):
            # TCKN ile çakışmayan 10 haneli rakamlar
            placeholder = f"[MASKED_VKN_{idx+1}]"
            mapping[placeholder] = vkn
            masked_text = masked_text.replace(vkn, placeholder)

        return masked_text, mapping

    def unmask_text(self, masked_text: str, mapping: Dict[str, str]) -> str:
        """
        Arayüzde gösterim için maskelenmiş verileri orijinal değerleriyle geri birleştirir.
        """
        if not masked_text or not mapping:
            return masked_text

        result = masked_text
        for placeholder, original_value in mapping.items():
            result = result.replace(placeholder, original_value)
        return result

pii_masker = PIIMasker()
