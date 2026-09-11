"""
Modül: GYK 1 Hariç Bırakma Notları Motoru (Negation Filter).
Genel Yorum Kuralı 1 (GYK 1) uyarınca, tarife sınıflandırması öncelikle
bölüm ve fasıl notlarındaki sarih hükümlere göre yapılır.

Bu motor, aday fasıllar arasında dışlama (exclusion) notlarını tarayarak
eşyanın asıl niteliği gereği girmemesi gereken fasılları eler.
Örnek: Plastik gövdeli bluetooth kulaklık için Fasıl 39 Not 2(p) uyarınca
Fasıl 39 elenerek Fasıl 85'e kilitlenir.
"""

import logging
import re
from typing import List, Dict, Any, Tuple, Optional
from api.schemas.product import ProductFeatures

logger = logging.getLogger("NegationEngine")

# Statik ve Yasal GYK 1 Fasıl Dışlama Notları Kütüphanesi
# Hukuki kaynak: TGTC Bölüm ve Fasıl Açıklama Notları (Gümrük Kanunu m. 15)
BUILTIN_EXCLUSION_RULES = [
    {
        "id": "NOTE_CH39_2P",
        "target_chapter": "39",
        "note_reference": "Fasıl 39 Not 2(p)",
        "condition_type": "ELECTRICAL_DEVICE",
        "keywords": [
            "kulaklık", "headphone", "earphone", "bluetooth", "hoparlör", "speaker",
            "telefon", "phone", "bilgisayar", "şarj", "adaptör", "kablo", "batarya",
            "akü", "motor", "elektronik", "devre", "sensör", "ekran", "lamba", "led",
            "kettle", "rezistans", "ısıtıcı", "kamera", "mikrofon"
        ],
        "excluded_chapter": "39",
        "redirect_chapter": "85",
        "legal_text": (
            "Fasıl 39 Not 2(p) Hükmü: Bölüm XVI kapsamına giren makineler, "
            "elektrikli cihazlar ve bunların aksamı (Fasıl 84 ve 85) bu fasla (Fasıl 39) girmez."
        )
    },
    {
        "id": "NOTE_CH39_2U",
        "target_chapter": "39",
        "note_reference": "Fasıl 39 Not 2(u)",
        "condition_type": "OPTICAL_INSTRUMENT",
        "keywords": ["mercek", "lens", "teleskop", "mikroskop", "optik", "tıbbi cihaz", "tansiyon"],
        "excluded_chapter": "39",
        "redirect_chapter": "90",
        "legal_text": (
            "Fasıl 39 Not 2(u) Hükmü: Fasıl 90 kapsamındaki optik elemanlar, "
            "tıbbi ve cerrahi aletler bu fasla girmez."
        )
    },
    {
        "id": "NOTE_CH73_1F",
        "target_chapter": "73",
        "note_reference": "Fasıl 73 Not 1(f)",
        "condition_type": "ELECTRICAL_MACHINERY",
        "keywords": ["motor", "jeneratör", "trafo", "elektrikli alet", "pompa"],
        "excluded_chapter": "73",
        "redirect_chapter": "84",
        "legal_text": (
            "Fasıl 73 Not 1(f) Hükmü: Bölüm XVI kapsamına giren makineler ve "
            "mekanik cihazlar (Fasıl 84 ve 85) Fasıl 73 kapsamına dahil edilmez."
        )
    },
    {
        "id": "NOTE_CH84_1A",
        "target_chapter": "84",
        "note_reference": "Bölüm XVI Not 1(a)",
        "condition_type": "TEXTILE_BELTS",
        "keywords": ["tekstil transmisyon kolonu", "dokuma kayış"],
        "excluded_chapter": "84",
        "redirect_chapter": "59",
        "legal_text": (
            "Bölüm XVI Not 1(a) Hükmü: Dokumaya elverişli maddelerden transmisyon kolonu "
            "veya kayışlar (Fasıl 59) bu bölüme girmez."
        )
    },
    {
        "id": "NOTE_SEC_XVI_1L",
        "target_chapter": "85",
        "note_reference": "Bölüm XVI Not 1(l)",
        "condition_type": "MUSICAL_INSTRUMENTS",
        "keywords": ["müzik aleti", "elektrogitar", "piyano", "org", "synthesizer"],
        "excluded_chapter": "85",
        "redirect_chapter": "92",
        "legal_text": (
            "Bölüm XVI Not 1(l) Hükmü: Fasıl 92'de yer alan müzik aletleri bu bölüme dahil değildir."
        )
    },
    {
        "id": "NOTE_CH95_1P",
        "target_chapter": "95",
        "note_reference": "Fasıl 95 Not 1(p)",
        "condition_type": "DRONE_AIRCRAFT",
        "keywords": ["insansız hava aracı", "iha", "drone (kamera taşıyıcı)", "havacılık"],
        "excluded_chapter": "95",
        "redirect_chapter": "88",
        "legal_text": (
            "Fasıl 95 Not 1(p) Hükmü: Fasıl 88 kapsamına giren insansız hava araçları "
            "oyuncak olarak kabul edilmez."
        )
    }
]


class NegationEngine:
    """
    GYK 1 Hariç Bırakma Notları (Negation Filter) Değerlendiricisi.
    """

    def __init__(self):
        self.rules = BUILTIN_EXCLUSION_RULES

    def apply_negation_filter(
        self,
        candidate_chapters: List[str],
        features: ProductFeatures,
        db_notes: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Aday fasılları GYK 1 dışlama notları süzgecinden geçirir.

        :param candidate_chapters: İlk aşamada önerilen aday fasıllar (örn: ['85', '90', '39'])
        :param features: Eşyanın yapılandırılmış özellikleri
        :param db_notes: Veritabanından çekilen dinamik chapter_section_notes kayıtları
        :return: (kalan_fasıllar, uygulanan_dışlama_kararları)
        """
        text_corpus = (
            f"{features.product_name} {getattr(features, 'commercial_name', '') or ''} "
            f"{features.primary_material or ''} {features.intended_use or ''} "
            f"{getattr(features, 'function', '') or ''} {' '.join(getattr(features, 'keywords', None) or [])}"
        ).lower()

        clean_candidates = [str(c).zfill(2) for c in candidate_chapters]
        excluded_set = set()
        applied_exclusions = []

        # 1. Dahili Kural Kütüphanesi Kontrolü
        for rule in self.rules:
            tgt_chap = rule["excluded_chapter"]
            if tgt_chap in clean_candidates:
                # Eşya tanımında dışlamayı tetikleyen anahtar özellik var mı?
                matched_kw = [kw for kw in rule["keywords"] if kw in text_corpus]
                if matched_kw:
                    excluded_set.add(tgt_chap)
                    redirection = rule.get("redirect_chapter")
                    applied_exclusions.append({
                        "rule_id": rule["id"],
                        "legal_reference": rule["note_reference"],
                        "excluded_chapter": tgt_chap,
                        "redirect_chapter": redirection,
                        "trigger_keywords": matched_kw[:3],
                        "legal_justification": rule["legal_text"],
                    })
                    logger.info(
                        "[NegationFilter] Fasıl %s elendi! Dayanak: %s. Yönlendirme: Fasıl %s. (Tetikleyici: %s)",
                        tgt_chap, rule["note_reference"], redirection, matched_kw[:3]
                    )

        # 2. Veritabanından gelen dinamik notlar kontrolü (varsa)
        if db_notes:
            for note in db_notes:
                tgt_chap = str(note.get("target_code", "")).zfill(2)
                if tgt_chap in clean_candidates and tgt_chap not in excluded_set:
                    rules = note.get("structured_rules") or {}
                    excluded_items = rules.get("excluded_items", [])
                    for item in excluded_items:
                        if str(item).lower() in text_corpus:
                            excluded_set.add(tgt_chap)
                            redir = rules.get("redirect_chapter")
                            applied_exclusions.append({
                                "rule_id": f"DB_NOTE_{str(note.get('id', ''))[:8]}",
                                "legal_reference": f"Fasıl {tgt_chap} Notu",
                                "excluded_chapter": tgt_chap,
                                "redirect_chapter": redir,
                                "trigger_keywords": [str(item)],
                                "legal_justification": note.get("raw_content", "")[:300],
                            })
                            break

        # Kalan adayları belirle
        surviving_chapters = [c for c in clean_candidates if c not in excluded_set]

        # Eğer yönlendirilen fasıl aday listesinde yoksa ve mantıklıysa ekle
        for exclusion in applied_exclusions:
            redir = exclusion.get("redirect_chapter")
            if redir and redir not in surviving_chapters:
                surviving_chapters.append(redir)

        # Aday kalmadıysa orijinal listeye dön (fail-open fallback)
        if not surviving_chapters:
            logger.warning("[NegationFilter] Dışlama sonucu aday kalmadı, orijinal liste korunuyor.")
            return clean_candidates, []

        return surviving_chapters, applied_exclusions


negation_engine = NegationEngine()
