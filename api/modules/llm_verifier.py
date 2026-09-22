"""Gemini adapter for closed-set tariff-node selection."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from api.config import settings
from api.schemas.predicate import CandidateSelection, CandidateSelectionStatus


logger = logging.getLogger("ClosedSetModelSelector")


class LLMFactVerifier:
    """Keeps the historical class name while exposing one focused operation."""

    @staticmethod
    def _config(narrowing: bool = False) -> Optional[Any]:
        try:
            from google.genai import types

            # İlk deneme deterministik ve ucuzdur. Daraltma denemesi ancak model
            # hiçbir seçeneği eşleştiremediğinde çalışır; aynı promptu aynı
            # sıcaklıkta tekrar göndermek deterministik kurulumda aynı cevabı
            # üretir, bu yüzden bütçe ve sıcaklık bilinçli olarak değiştirilir.
            return types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_budget=settings.THINKING_BUDGET_EXCLUSION if narrowing else 0
                ),
                temperature=0.3 if narrowing else 0.0,
                response_mime_type="application/json",
            )
        except Exception:
            return None

    _LEVEL_PREFIX = {"CHAPTER": 2, "HEADING": 4, "SUBHEADING": 6, "GTIP": 8}

    @classmethod
    def _precedent_evidence(
        cls,
        level: str,
        nodes: List[Dict[str, Any]],
        precedents: Optional[List[Any]],
    ) -> List[Dict[str, Any]]:
        """Bu seviyedeki seçeneklerle aynı ön-eki paylaşan emsalleri seçer.

        Emsaller bağlayıcı değildir (başka kişiye verilmiş BTB/EBTI kararları),
        fakat aynı eşya için idarenin daha önce ne yaptığını gösterir. Seviyeyle
        ilgisiz emsal prompta gürültü katacağı için ön-ek filtresi uygulanır.
        """
        if not precedents:
            return []
        width = cls._LEVEL_PREFIX.get(level, 4)
        allowed = {
            re.sub(r"\D", "", str(node.get("gtip_code") or ""))[:width]
            for node in nodes
        }
        allowed.discard("")

        evidence: List[Dict[str, Any]] = []
        for item in precedents:
            code = re.sub(r"\D", "", str(getattr(item, "gtip_code", "") or getattr(item, "cn_code", "")))
            if not code:
                continue
            # CHAPTER seviyesinde tüm fasıllar seçenek olduğundan filtre elemez;
            # alt seviyelerde yalnız kardeş dallara ait emsaller kalır.
            if allowed and code[:width] not in allowed:
                continue
            evidence.append({
                "kaynak": str(getattr(item, "source_type", None) or "EU_EBTI"),
                "referans_no": str(getattr(item, "btb_no", None) or getattr(item, "reference_no", "")),
                "karar_kodu": str(getattr(item, "gtip_code", None) or getattr(item, "cn_code", "")),
                "esya_tanimi": str(getattr(item, "product_description", ""))[:600],
                "hukuki_gerekce": str(getattr(item, "legal_justification", ""))[:400],
                "benzerlik": round(float(getattr(item, "similarity_score", 0.0) or 0.0), 3),
            })
            if len(evidence) >= 4:
                break
        return evidence

    def select_tariff_node(
        self,
        raw_text: str,
        level: str,
        nodes: List[Dict[str, Any]],
        _no_match_retries: int = 2,
        *,
        precedents: Optional[List[Any]] = None,
        chapter_notes: Optional[str] = None,
        narrowing: bool = False,
    ) -> CandidateSelection:
        """Select one server-owned node without accepting a model-written code."""
        bounded_nodes = nodes[:250]
        if not bounded_nodes:
            return CandidateSelection(
                status=CandidateSelectionStatus.NO_MATCH,
                reasoning_points=["Bu tarife dalında resmî bir seçenek bulunamadı."],
            )

        option_map = {f"N{index + 1}": node for index, node in enumerate(bounded_nodes)}
        if settings.USE_GCP_EMULATOR or settings.ENVIRONMENT == "testing":
            return CandidateSelection(
                status=CandidateSelectionStatus.SELECT,
                selected_candidate_id="N1",
                reasoning_points=["Test ortamında ilk kapalı-küme seçeneği kullanıldı."],
                applied_gir_keys=["GIR_1", "GIR_6"],
                cited_chapter_notes=[],
            )

        payload = [
            {
                "option_id": option_id,
                "official_code": str(node.get("gtip_code") or ""),
                "official_description": str(
                    node.get("branch_context") or node.get("description") or ""
                )[:1800],
            }
            for option_id, node in option_map.items()
        ]
        evidence = self._precedent_evidence(level, bounded_nodes, precedents)
        evidence_block = (
            "EMSAL KARARLAR (DELİLDİR, BAĞLAYICI DEĞİLDİR — başka kişilere verilmiş "
            "BTB/EBTI kararlarıdır):\n"
            "- Emsalle aynı yönde seçim yaparsan reasoning_points içinde referans_no yaz.\n"
            "- Ürün emsalden maddi olarak farklıysa emsali AÇIKÇA reddet ve farkı yaz.\n"
            "- Emsal, resmî seçenek metni veya fasıl notuyla çelişirse METİN VE NOT ÜSTÜNDÜR.\n"
            f"{json.dumps(evidence, ensure_ascii=False)}\n\n"
        ) if evidence else ""

        notes_block = (
            "İLGİLİ FASIL NOTLARI (RESMÎ METİN — GİR 1 uyarınca pozisyon metinleriyle "
            "birlikte BAĞLAYICIDIR). Özellikle 'bu fasıla dahil değildir' biçimindeki "
            "dışlama hükümlerine uy:\n"
            f"{str(chapter_notes)[:6000]}\n\n"
        ) if chapter_notes else ""

        # Daraltma denemesi: NO_MATCH bir çıkmazdır. Model tam eşleşme bulamasa
        # bile en yakın kardeş dalları verebilirse, sistem ölü uç yerine
        # müşavire sorulabilir sınırlı bir soru üretir.
        narrowing_block = (
            "ÖNEMLİ — İKİNCİ DENEME: Önceki denemende hiçbir seçeneği eşleştiremedin.{nl}"
            "- Tam eşleşme bulamıyorsan bile EN YAKIN 2-4 seçeneği alternative_candidate_ids "
            "olarak ver ve status=INSUFFICIENT_INFORMATION döndür.{nl}"
            "- NO_MATCH yalnız ürün bu tarife dalıyla tamamen ilgisizse geçerlidir "
            "(örneğin canlı hayvan seçenekleri arasında elektronik bir cihaz).{nl}"
            "- Ürün bu dala ait ama hangi alt ayrıma girdiği belirsizse bu bir NO_MATCH "
            "değil, bilgi eksikliğidir.{nl}{nl}"
        ).format(nl=chr(10)) if narrowing else ""

        level_rule = (
            "11. CHAPTER bir yönlendirme seviyesidir: ürünün esas niteliği, adı ve işlevine göre en uygun faslı mutlaka "
            "SELECT et. Bu seviyede malzeme gibi ayrıntıları sorma ve INSUFFICIENT_INFORMATION kullanma."
            if level == "CHAPTER"
            else "11. Seçimi ürünün esas niteliği ve işlevine göre yap; tali malzemeyi ancak resmî ayrım bunu gerektiriyorsa kullan."
        )
        prompt = (
            "Sen Türk Gümrük Tarife Cetveli ve WCO Armonize Sistem sınıflandırma uzmanısın. "
            "Ürünü, aşağıdaki SUNUCU TARAFINDAN SAĞLANAN resmî seçeneklerden birine bağla.\n\n"
            "KATI HUKUKİ SINIFLANDIRMA VE YORUM KURALLARI (GYK / GİR):\n"
            "1. YENİ KOD UYDURMA: Yeni GTİP/fasıl/pozisyon kodu yazma veya düzeltme; yalnız option_id döndür.\n"
            "2. KAPALI KÜME: Seçenekler dışında bilgi uydurma. Ürün açıkça bir seçeneğe uyuyorsa SELECT kullan.\n"
            "3. GYK 1 & BÖLÜM/FASIL DIŞLAMA NOTLARI (EXCLUSION NOTES):\n"
            "   - Sınıflandırma öncelikle tarife pozisyonu metinlerine ve fasıl notlarına göre yapılır.\n"
            "   - Çerçeveli, profilli veya mekanizmalı mimari kapama, bölme, doğrama, pencere, kapı ve balkon sistemleri "
            "(örneğin 'cam balkon sistemi', 'balkon camlama', 'kış bahçesi', 'sürme/katlanır cam sistemleri'), "
            "FASIL 70 (Cam) KAPSAMI DIŞINDADIR (Fasıl 70 notları uyarınca).\n"
            "   - Bu tür sistemler taşıyıcı/çerçeve malzemesine göre sınıflandırılır: Alüminyum profilli ise FASIL 76 "
            "(özellikle 76.10 pozisyonu: Alüminyum inşaat ve inşaat aksamı; kapılar, pencereler ve çerçeveleri), "
            "demir/çelik ise FASIL 73 (73.08), plastik/PVC ise FASIL 39 (39.25). Asla Fasıl 70'e yönlendirme!\n"
            "4. GYK 2(a) - DEMONTE / SÖKÜLMÜŞ EŞYA: Demonte, profil veya parça kitleri halinde sevk edilen sistemler, "
            "monte edilmiş yapının esas karakterini taşıyorsa bitmiş mamul pozisyonunda (örn. 76.10) sınıflandırılır.\n"
            "5. GYK 3(a) - ÖZEL TANIM GENEL TANIMA ÜSTÜNDÜR: Eşyanın mimari işlevini doğrudan tanımlayan pozisyon "
            "(örn. 76.10: Alüminyum inşaat aksamı, kapılar, pencereler, çerçeveler), sırf hammaddeyi genel olarak belirten "
            "pozisyona (örn. Fasıl 70 / 70.05 / 70.07 ham cam) daima tercih edilir.\n"
            "6. GYK 3(b) - KOMPOZİT EŞYADA ESAS KARAKTER: Farklı maddelerden oluşan eşyalarda (örn. alüminyum ray/profil + "
            "cam paneller), sisteme taşıma, katlanma, sürme mekanizması ve mimari dayanım sağlayan alüminyum strüktür esas karakteri verir.\n"
            "7. GEREKSİZ CAM İMALAT SORULARI SORMA: Cam balkon ve mimari doğrama sistemlerinde kullanıcıya camın üretim şeklini "
            "(float, çekme, temperli/lamine - 7004/7005/7007) sorma! Ürün hammadde camı değildir; doğrudan 76.10 / 7610.10 dalına ilerle.\n"
            "8. DAR/İSTİSNAİ DALLAR: Tohumluk, sivil hava taşıtı, soğuk hava deposu, çocuklar için, tıbbi kullanım gibi dar dalları "
            "yalnız ürün metninde bunu destekleyen olumlu kanıt varsa seç. Böyle kanıt yoksa mevcut genel/kalıntı 'diğerleri' dalını SELECT et.\n"
            "9. SORU SINIRI (INSUFFICIENT_INFORMATION): Ancak seçenekler arasındaki ayrım için gerçekten gerekli, kullanıcıca "
            "gözlenebilir bir teknik özellik eksikse INSUFFICIENT_INFORMATION kullan, iki ila dört alternative_candidate_ids ve tek "
            "somut Türkçe question_text döndür. Soru yalnız malzeme, işlev, ölçü veya fiziksel nitelik hakkında olabilir; tarife kodu seçtiremez.\n"
            "10. EŞLEŞME YOKSA: Hiçbir seçenek eşleşmiyorsa NO_MATCH kullan.\n"
            f"{level_rule}\n\n"
            f"SEVİYE: {level}\n"
            # Seçenek listesi bu seviye için SABİTTİR (yalnız fasıl listesi
            # ~20.000 token). Değişken ürün metni bu bloktan önce gelirse
            # istekler arasında ortak ön-ek kalmaz ve prompt önbelleklemesi
            # imkânsızlaşır; bu yüzden sabit blok değişken bloktan ÖNCE gelir.
            f"RESMÎ KAPALI SEÇENEKLER: {json.dumps(payload, ensure_ascii=False)}\n\n"
            f"{notes_block}"
            f"{evidence_block}"
            f"{narrowing_block}"
            f"<product_data>{raw_text}</product_data>\n"
            "Yalnız şu JSON biçimini döndür: "
            "{\"status\":\"SELECT|INSUFFICIENT_INFORMATION|NO_MATCH\","
            "\"selected_candidate_id\":\"N1 veya null\","
            "\"alternative_candidate_ids\":[\"N1\",\"N2\"],"
            "\"question_text\":\"Türkçe soru veya null\","
            "\"reasoning_points\":[\"kısa Türkçe gerekçe\"],"
            "\"applied_gir_keys\":[\"GIR_1\",\"GIR_3A\",\"GIR_3B\",\"GIR_6\"],"
            "\"cited_chapter_notes\":[\"70\",\"76\"]}"
        )

        try:
            from api.modules.vertex_client import get_genai_client

            for attempt in range(1, 4):
                try:
                    response = get_genai_client().models.generate_content(
                        model=settings.REASONING_LLM_MODEL,
                        contents=prompt,
                        config=self._config(narrowing),
                    )
                    break
                except Exception as exc:
                    if attempt == 3:
                        raise
                    logger.warning(
                        "Tariff node selection attempt %s/3 failed; retrying: %s",
                        attempt,
                        exc,
                    )
                    time.sleep(0.35 * attempt)
            match = re.search(r"\{.*\}", response.text or "", re.DOTALL)
            data = json.loads(match.group(0) if match else (response.text or ""))
            data["alternative_candidate_ids"] = data.get("alternative_candidate_ids") or []
            data["reasoning_points"] = data.get("reasoning_points") or []
            data["applied_gir_keys"] = data.get("applied_gir_keys") or []
            data["cited_chapter_notes"] = [str(c).zfill(2) for c in (data.get("cited_chapter_notes") or [])]

            # Gelişmiş deterministik fallback: Model reasoning_points içine GİR veya fasıl yazmışsa
            # ama applied_gir_keys listesine eklemeyi unutmuşsa bile kural kodlarını otomatik tamamla
            full_reasoning_text = " ".join(data["reasoning_points"])
            for g_code, aliases in [
                ("GIR_1", ["GİR 1", "GYK 1", "GIR 1"]),
                ("GIR_2A", ["GİR 2(a)", "GYK 2(a)", "GIR 2A", "GİR 2A", "GYK 2A"]),
                ("GIR_2B", ["GİR 2(b)", "GYK 2(b)", "GIR 2B", "GİR 2B", "GYK 2B"]),
                ("GIR_3A", ["GİR 3(a)", "GYK 3(a)", "GIR 3A", "GİR 3A", "GYK 3A"]),
                ("GIR_3B", ["GİR 3(b)", "GYK 3(b)", "GIR 3B", "GİR 3B", "GYK 3B"]),
                ("GIR_3C", ["GİR 3(c)", "GYK 3(c)", "GIR 3C", "GİR 3C", "GYK 3C"]),
                ("GIR_4", ["GİR 4", "GYK 4", "GIR 4"]),
                ("GIR_5A", ["GİR 5(a)", "GYK 5(a)", "GIR 5A"]),
                ("GIR_5B", ["GİR 5(b)", "GYK 5(b)", "GIR 5B"]),
                ("GIR_6", ["GİR 6", "GYK 6", "GIR 6"]),
            ]:
                if any(al in full_reasoning_text for al in aliases) and g_code not in data["applied_gir_keys"]:
                    data["applied_gir_keys"].append(g_code)

            for ch_match in re.findall(r"fas[iı]l\s*(\d{1,2})", full_reasoning_text, re.IGNORECASE):
                ch_z = ch_match.zfill(2)
                if ch_z not in data["cited_chapter_notes"]:
                    data["cited_chapter_notes"].append(ch_z)

            selection = CandidateSelection(**data)
            valid_ids = set(option_map)
            if selection.status == CandidateSelectionStatus.SELECT:
                if selection.selected_candidate_id not in valid_ids:
                    raise ValueError("Model kapalı seçenek kümesi dışında kimlik döndürdü.")
            else:
                selection.selected_candidate_id = None
            selection.alternative_candidate_ids = [
                option_id
                for option_id in selection.alternative_candidate_ids
                if option_id in valid_ids
            ][:4]
            should_retry_choice = (
                selection.status == CandidateSelectionStatus.NO_MATCH
                or (level == "CHAPTER" and selection.status != CandidateSelectionStatus.SELECT)
            )
            if should_retry_choice and _no_match_retries > 0:
                logger.warning(
                    "Tariff node selection returned %s at level=%s; narrowing retry (%s left)",
                    selection.status,
                    level,
                    _no_match_retries,
                )
                time.sleep(0.25)
                return self.select_tariff_node(
                    raw_text,
                    level,
                    nodes,
                    _no_match_retries=_no_match_retries - 1,
                    # Yeniden denemede emsal ve fasıl notu bağlamı korunmalıdır;
                    # aksi halde retry ilk denemeden daha az bilgiyle çalışır.
                    precedents=precedents,
                    chapter_notes=chapter_notes,
                    # Aynı promptu tekrar göndermek yerine modelden en yakın
                    # dalları istemek, çıkmazı sorulabilir bir soruya çevirir.
                    narrowing=True,
                )
            return selection
        except Exception as exc:
            logger.error("Tariff node selection failed closed: %s", exc)
            return CandidateSelection(
                status=CandidateSelectionStatus.NO_MATCH,
                reasoning_points=["Model yanıtı kapalı seçenek sözleşmesine bağlanamadı."],
            )


llm_verifier = LLMFactVerifier()
