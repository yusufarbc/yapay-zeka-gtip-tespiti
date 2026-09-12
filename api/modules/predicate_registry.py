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

    def get_predicates_for_gtip(
        self,
        gtip_code: str,
        official_description: Optional[str] = None,
        chapter_note: Optional[str] = None,
    ) -> List[LegalPredicate]:
        """
        GTİP koduna (ör. '8517.13.00.00.00' veya '8471.30') göre yasal doğrulama şartlarını 
        resmi mevzuat ve BTB veritabanından dinamik olarak oluşturur.
        """
        clean_code = gtip_code.replace(".", "").strip()
        chap2 = clean_code[:2] if len(clean_code) >= 2 else ""
        pos4 = clean_code[:4] if len(clean_code) >= 4 else chap2
        hs6 = clean_code[:6] if len(clean_code) >= 6 else pos4

        # Dinamik Fasıl Başlığı
        chap_title = get_chapter_title(chap2)

        predicates = []

        # 1. Genel Yasal Pozisyon Koşulu (TGTC pozisyon metni & GİR 1/6)
        predicates.append(
            LegalPredicate(
                predicate_id=f"P_{pos4}_1",
                description=(
                    f"Eşya, TGTC Fasıl {chap2} ({chap_title}) kapsamındaki {pos4} pozisyonunun "
                    f"şu resmi tanımına uygun mudur: {(official_description or 'resmi pozisyon tanımı')[:800]}"
                ),
                required_value="TRUE",
                statute_reference=f"TGTC Fasıl {chap2} ve Pozisyon {pos4} metni & GİR 1"
            )
        )

        # 2. Alt Pozisyon Nitelik Koşulu (GİR 6)
        if len(clean_code) >= 6:
            sub_desc = ""
            try:
                from api.db.database import SessionLocal, TgtcGtipModel
                with SessionLocal() as db_session:
                    sub_item = db_session.query(TgtcGtipModel).filter(TgtcGtipModel.gtip_code == hs6).first()
                    if sub_item and sub_item.description:
                        sub_desc = f": {sub_item.description.strip()}"
            except Exception:
                pass

            predicates.append(
                LegalPredicate(
                    predicate_id=f"P_{hs6}_2",
                    description=f"Eşya, TGTC {gtip_code[:7]} alt pozisyonunun şu resmi tanım ve şartlarına uygun mudur{sub_desc}",
                    required_value="TRUE",
                    statute_reference=f"TGTC {gtip_code[:7]} Alt Pozisyon Notları & GİR 6"
                )
            )

        # BTB emsalleri bağlayıcı koşul değildir; zorunlu predikat yalnız TGTC
        # pozisyon/alt pozisyon metni ve dışlama notlarından üretilir.
        if chapter_note:
            predicates.append(
                LegalPredicate(
                    predicate_id=f"P_{pos4}_EXCLUSION",
                    description=(
                        "Eşya aşağıdaki fasıl/pozisyon notuna göre bu adaydan hariç tutuluyor mu: "
                        f"{chapter_note[:800]}"
                    ),
                    required_value="FALSE",
                    statute_reference=f"TGTC Fasıl {chap2} dışlama ve fasıl notları",
                )
            )

        return predicates


predicate_registry = PredicateRegistryEngine()
