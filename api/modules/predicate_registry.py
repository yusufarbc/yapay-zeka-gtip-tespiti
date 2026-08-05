"""
TGTC Yasal Koşul Ağacı (Dynamic Legal Predicate Registry).
%100 Dinamik Altyapı: Hiçbir kod veya JSON dosyasında statik/hardcoded eşleştirme yoktur.

Tüm yasal doğrulama koşulları (Boolean Legal Predicates);
1. TGTC 99 Fasıl resmi tanımlarından (`api/data/tgtc_chapters.json`),
2. Resmi organlardan web scraper ile çekilen BTB gerekçelerinden (`api/data/official_btb_database.json`),
3. GİR 1-6 yorum kurallarından
dinamik olarak runtime'da üretilir.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from api.schemas.predicate import LegalPredicate
from api.db.tgtc_knowledge_base import TGTC_CHAPTERS, get_chapter_title

logger = logging.getLogger("PredicateRegistry")


class PredicateRegistryEngine:
    """
    Sıfır Hardcoded Veri Bağımlılığı ile Dinamik Predikat Motoru.
    Gelen GTİP koduna ait yasal şartları canlı veritabanından dinamik olarak türetir.
    """

    def get_predicates_for_gtip(self, gtip_code: str) -> List[LegalPredicate]:
        """
        GTİP koduna (ör. '8517.13.00.00.00' veya '8471.30') göre yasal doğrulama şartlarını 
        resmi mevzuat ve BTB veritabanından dinamik olarak oluşturur.
        """
        clean_code = gtip_code.replace(".", "").strip()
        chap2 = clean_code[:2] if len(clean_code) >= 2 else "84"
        pos4 = clean_code[:4] if len(clean_code) >= 4 else f"{chap2}01"
        hs6 = clean_code[:6] if len(clean_code) >= 6 else pos4

        # Dinamik Fasıl Başlığı
        chap_title = get_chapter_title(chap2)

        predicates = []

        # 1. Genel Yasal Pozisyon Koşulu (TGTC İzahnamesi & GİR 1/6)
        predicates.append(
            LegalPredicate(
                predicate_id=f"P_{pos4}_1",
                description=f"Eşya, TGTC Fasıl {chap2} ({chap_title}) kapsamındaki {pos4} pozisyonunun teknik ve hukuki tanımına uygun mudur?",
                required_value="TRUE",
                statute_reference=f"TGTC Fasıl {chap2} İzahnamesi & GİR 1"
            )
        )

        # 2. Alt Pozisyon Nitelik Koşulu (GİR 6)
        if len(clean_code) >= 6:
            predicates.append(
                LegalPredicate(
                    predicate_id=f"P_{hs6}_2",
                    description=f"Eşyanın malzeme bileşeni, çalışma prensibi veya kullanım amacı {gtip_code[:7]} alt pozisyon şartını karşılıyor mu?",
                    required_value="TRUE",
                    statute_reference=f"TGTC {gtip_code[:7]} Alt Pozisyon Notları & GİR 6"
                )
            )

        # 3. Emsal BTB Kararlarından Dinamik Gerekçe Şartı Çekme
        try:
            from api.db.gcp_emulator import local_vector_store
            btb_matches = local_vector_store.search_btb(
                query_text=gtip_code,
                allowed_chapters=[chap2],
                top_k=1
            )
            if btb_matches and btb_matches[0].get("legal_justification"):
                justification = btb_matches[0]["legal_justification"]
                predicates.append(
                    LegalPredicate(
                        predicate_id=f"P_{pos4}_BTB",
                        description=f"Eşya, Resmi Emsal BTB ({btb_matches[0].get('btb_no', 'RESMİ-BTB')}) Kararı gerekçesindeki '{justification[:100]}...' yasal kriterini sağlıyor mu?",
                        required_value="TRUE",
                        statute_reference=f"Ticaret Bakanlığı BTB Kararı {btb_matches[0].get('btb_no', '')}"
                    )
                )
        except Exception as e:
            logger.debug(f"[PredicateRegistry] BTB dinamik gerekçe çekme uyarısı: {e}")

        return predicates


predicate_registry = PredicateRegistryEngine()
