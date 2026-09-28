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


def option_id(index: int) -> str:
    """0-tabanlı sırayı harf kimliğine çevirir: A, B, ... Z, AA, AB, ...

    Kimlikler önceden N1, N2, ... biçimindeydi ve tarife kodlarıyla tehlikeli
    biçimde hizalıydı: fasıl listesinde N1..N76 tam olarak Fasıl 01..76'ya denk
    geliyor, Fasıl 77 Armonize Sistem'de ayrıldığı için sonrası bir kayıyordu.
    Model "Fasıl 85" demek isteyip N85 yazdığında sunucu Fasıl 86 çözüyordu —
    sessiz ve sistematik bir hata (üretimde kablosuz kulaklık böyle kayboldu).

    Harf kimlikleri hiçbir tarife koduyla karıştırılamaz.
    """
    if index < 0:
        raise ValueError("Seçenek sırası negatif olamaz")
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


class LLMFactVerifier:
    """Keeps the historical class name while exposing one focused operation."""

    @staticmethod
    def _call_timeout_ms(deadline: Optional[float]) -> int:
        """Bu çağrıya ayrılan süre: kalan bütçenin bir kısmı, tavanı LLM_TIMEOUT_MS.

        Sabit 15 sn'lik timeout, bütçe kavramı olmadığında tek bir yavaş çağrının
        hattın tamamını yemesine izin veriyordu: CHAPTER seviyesinde iki kez 504
        alınca 32 saniyenin tamamı tükeniyor ve alt seviyeler hiç denenmiyordu.

        Kalan sürenin tamamı verilmez; geriye kalan seviyeler için pay bırakılır.
        Taban 4 sn: bundan kısası hiçbir çağrının tamamlanmasına yetmez, denemek
        bütçeyi boşa harcamak olur.
        """
        ceiling = settings.LLM_TIMEOUT_MS
        if deadline is None:
            return ceiling
        remaining_ms = max(0.0, (deadline - time.monotonic()) * 1000.0)
        return int(max(4000, min(ceiling, remaining_ms * 0.6)))

    @staticmethod
    def _config(
        narrowing: bool = False,
        timeout_ms: Optional[int] = None,
        level: Optional[str] = None,
    ) -> Optional[Any]:
        try:
            from google.genai import types

            # İlk deneme deterministik ve ucuzdur. Daraltma denemesi ancak model
            # hiçbir seçeneği eşleştiremediğinde çalışır; aynı promptu aynı
            # sıcaklıkta tekrar göndermek deterministik kurulumda aynı cevabı
            # üretir, bu yüzden bütçe ve sıcaklık bilinçli olarak değiştirilir.
            return types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_budget=LLMFactVerifier._thinking_budget(narrowing, level)
                ),
                temperature=0.3 if narrowing else 0.0,
                response_mime_type="application/json",
                http_options=types.HttpOptions(
                    timeout=timeout_ms or settings.LLM_TIMEOUT_MS
                ),
            )
        except Exception:
            return None

    @staticmethod
    def _thinking_budget(narrowing: bool, level: Optional[str]) -> int:
        """CHAPTER yönlendirmesi düşünme payı ister; alt seviyelerde ilk deneme 0'dır."""
        if level == "CHAPTER":
            return max(settings.THINKING_BUDGET_CHAPTER, settings.THINKING_BUDGET_EXCLUSION if narrowing else 0)
        return settings.THINKING_BUDGET_EXCLUSION if narrowing else 0

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
        rejected_codes: Optional[List[str]] = None,
        deadline: Optional[float] = None,
    ) -> CandidateSelection:
        """Select one server-owned node without accepting a model-written code."""
        bounded_nodes = nodes[:250]
        if not bounded_nodes:
            return CandidateSelection(
                status=CandidateSelectionStatus.NO_MATCH,
                reasoning_points=["Bu tarife dalında resmî bir seçenek bulunamadı."],
            )

        if deadline is not None and time.monotonic() >= deadline:
            logger.warning("Süre bütçesi doldu; seviye=%s için model çağrılmadı.", level)
            return CandidateSelection(
                status=CandidateSelectionStatus.NO_MATCH,
                reasoning_points=["Analiz süre bütçesi doldu."],
            )

        option_map = {option_id(index): node for index, node in enumerate(bounded_nodes)}
        if settings.USE_GCP_EMULATOR or settings.ENVIRONMENT == "testing":
            return CandidateSelection(
                status=CandidateSelectionStatus.SELECT,
                selected_candidate_id=option_id(0),
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

        # Geri alma: reddedilen dal seçenek listesinden ÇIKARILMAZ. Kimlikler
        # konumsaldır; çıkarmak tüm id'leri kaydırır ve model aynı id'yi
        # döndürdüğünde komşu dala geçilir (üretimde 86 -> 87 böyle oluştu).
        # Liste sabit tutulur, dışlama modele açıkça bildirilir.
        # Model seçimi harf kimliğiyle yapar; yalnız tarife kodunu söylemek
        # yetmiyordu (canlıda reddedilen "44" yine "AR" kimliğiyle seçildi).
        rejected_labels = [
            f"{oid} ({re.sub(r'[^0-9]', '', str(node.get('gtip_code') or ''))})"
            for oid, node in option_map.items()
            if re.sub(r"\D", "", str(node.get("gtip_code") or "")) in set(rejected_codes or [])
        ] or list(rejected_codes or [])
        rejection_block = (
            "ÖNCEKİ DENEME BAŞARISIZ: {codes} seçeneğini seçtin, fakat o dalın "
            "altında ürüne uyan hiçbir alt dal bulunamadı.{nl}"
            "- Bu dal(lar)ı TEKRAR SEÇME.{nl}"
            "- Ürünün esas niteliğini yeniden değerlendir ve FARKLI bir dal seç.{nl}"
            "- Komşu numaraya kaymak yerine ürünün işlevine göre karar ver.{nl}{nl}"
        ).format(codes=", ".join(rejected_labels), nl=chr(10)) if rejected_codes else ""

        level_rule = (
            "- CHAPTER bir yönlendirme seviyesidir: ürünün esas niteliği, adı ve işlevine göre en uygun faslı mutlaka "
            "SELECT et. Bu seviyede malzeme gibi ayrıntıları sorma ve INSUFFICIENT_INFORMATION kullanma.\n"
            # Genel ilke (GYK 3(a) ve malzeme fasıllarının dışlama notları);
            # belirli ürün veya kod içermez. Ölçümde model bunu tutarlı
            # uygulamıyordu: aynı prompt ahşap sandalyeyi malzeme faslına,
            # metal masayı mobilyaya gönderebiliyordu.
            "- İŞLEV MALZEMEDEN ÖNCE GELİR (GYK 1 ve GYK 3(a) gereği): Önce eşyanın NE OLDUĞUNU belirle (ne işe yarayan hangi tür eşya). Eşyayı bu "
            "türüyle tanımlayan bir fasıl varsa onu seç; yalnız yapıldığı malzemeyi kapsayan fasıl (ahşap, plastik, metal, "
            "cam, kağıt vb. eşya fasılları) ikinci plandadır. Malzeme faslını yalnız eşya türüyle başka bir fasılda "
            "tanımlanmıyorsa seç. Malzeme fasıllarının notları, başka fasıllarda türüyle tanımlanan eşyayı genellikle "
            "kapsam dışında bırakır."
            if level == "CHAPTER"
            else "11. Seçimi ürünün esas niteliği ve işlevine göre yap; tali malzemeyi ancak resmî ayrım bunu gerektiriyorsa kullan."
        )
        prompt = (
            "Sen Türk Gümrük Tarife Cetveli ve WCO Armonize Sistem sınıflandırma uzmanısın. "
            "Ürünü, aşağıdaki SUNUCU TARAFINDAN SAĞLANAN resmî seçeneklerden birine bağla.\n\n"
            # Talimatlar numarasızdır: numaralı listede model "12. madde"yi
            # "GYK 12" diye gerekçeye yazıyordu; GYK yalnız 1-6 arasıdır.
            "SEÇİM TALİMATLARI (gerekçede bu talimatlara değil; yalnız GYK 1-6'ya, resmî seçenek metnine "
            "veya fasıl notuna atıf yap):\n"
            "- YENİ KOD UYDURMA: Yeni GTİP/fasıl/pozisyon kodu yazma veya düzeltme; yalnız option_id döndür.\n"
            "   option_id HARF kimliğidir (A, B, ... AA, AB). Tarife koduyla İLGİSİZDİR; "
            "seçmek istediğin seçeneğin option_id alanını birebir kopyala.\n"
            "- KAPALI KÜME: Seçenekler dışında bilgi uydurma. Ürün açıkça bir seçeneğe uyuyorsa SELECT kullan.\n"
            # Bu kurallar genel yorum kurallarıdır; belirli ürün veya kod için kural
            # YAZILMAZ. Ürüne özel kural (ör. "cam balkon -> 76.10") modele resmî
            # notta bulunmayan bir hükmü "fasıl notları uyarınca" diye aktarttı.
            # Ayrım resmî metinden, fasıl notlarından ve emsallerden gelmelidir.
            "- GYK 1: Sınıflandırma öncelikle tarife pozisyonu metinlerine ve bölüm/fasıl notlarına göre yapılır. "
            "Aşağıda verilen fasıl notlarındaki dışlama hükümlerine uy.\n"
            "- ATIF DÜRÜSTLÜĞÜ: Yalnız bu promptta sana verilen resmî seçenek metnine, fasıl notuna veya emsale atıf yap. "
            "Sana verilmeyen bir not hükmünü 'fasıl notları uyarınca' diye yazma; notta açıkça geçmeyen bir kuralı notun "
            "hükmüymüş gibi sunma. Ürün profilinde '(model varsayımı, teyit edilmedi)' diye işaretli bilgiyi gerekçede "
            "beyan edilmiş gibi yazma; kullanırsan 'varsayılan' olduğunu belirt.\n"
            "- GYK 2(a): Eksik, bitmemiş, demonte veya sökülmüş halde sunulan eşya, tamamlanmış eşyanın esas niteliğini "
            "taşıyorsa tamamlanmış eşyanın pozisyonunda sınıflandırılır.\n"
            "- GYK 3(a): Eşyayı en özel şekilde tanımlayan pozisyon, daha genel tanımlayan pozisyona tercih edilir.\n"
            "- GYK 3(b): Karışımlar ve farklı maddelerden oluşan eşyalar, esas niteliğini veren madde veya parçaya göre "
            "sınıflandırılır.\n"
            "- DAR/İSTİSNAİ DALLAR: Tohumluk, sivil hava taşıtı, soğuk hava deposu, çocuklar için, tıbbi kullanım gibi dar dalları "
            "yalnız ürün metninde bunu destekleyen olumlu kanıt varsa seç. Böyle kanıt yoksa mevcut genel/kalıntı 'diğerleri' dalını SELECT et.\n"
            "- SORU SINIRI (INSUFFICIENT_INFORMATION): Ancak seçenekler arasındaki ayrım için gerçekten gerekli, kullanıcıca "
            "gözlenebilir bir teknik özellik eksikse INSUFFICIENT_INFORMATION kullan, iki ila dört alternative_candidate_ids ve tek "
            "somut Türkçe question_text döndür. Soru yalnız malzeme, işlev, ölçü veya fiziksel nitelik hakkında olabilir; tarife kodu seçtiremez.\n"
            "- EŞLEŞME YOKSA: Hiçbir seçenek eşleşmiyorsa NO_MATCH kullan.\n"
            f"{level_rule}\n\n"
            f"SEVİYE: {level}\n"
            # Seçenek listesi bu seviye için SABİTTİR (yalnız fasıl listesi
            # ~20.000 token). Değişken ürün metni bu bloktan önce gelirse
            # istekler arasında ortak ön-ek kalmaz ve prompt önbelleklemesi
            # imkânsızlaşır; bu yüzden sabit blok değişken bloktan ÖNCE gelir.
            f"RESMÎ KAPALI SEÇENEKLER: {json.dumps(payload, ensure_ascii=False)}\n\n"
            f"{notes_block}"
            f"{evidence_block}"
            f"{rejection_block}"
            f"{narrowing_block}"
            f"<product_data>{raw_text}</product_data>\n"
            "Yalnız şu JSON biçimini döndür: "
            "{\"status\":\"SELECT|INSUFFICIENT_INFORMATION|NO_MATCH\","
            "\"selected_candidate_id\":\"A veya null\","
            "\"alternative_candidate_ids\":[\"A\",\"B\"],"
            "\"question_text\":\"Türkçe soru veya null\","
            "\"reasoning_points\":[\"1-3 kısa Türkçe cümle: seçimi belirleyen ürün özelliği ve "
            "dayandığın GİR kuralı veya fasıl notu\"],"
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
                        config=self._config(narrowing, self._call_timeout_ms(deadline), level),
                    )
                    break
                except Exception as exc:
                    if attempt == 3:
                        raise
                    # 429 (kota) ve 504 (deadline) 0.35 saniyede düzelmez; üstel
                    # bekleme uygulanır. Bütçe kalmadıysa beklemek yerine vazgeç:
                    # geriye kalan süre sonraki seviyeler için daha değerlidir.
                    backoff = (settings.PROVIDER_RETRY_BASE_MS / 1000.0) * (2 ** (attempt - 1))
                    if deadline is not None and time.monotonic() + backoff >= deadline:
                        logger.warning(
                            "Sağlayıcı hatası sonrası bütçe kalmadı; yeniden denenmiyor: %s", exc
                        )
                        raise
                    logger.warning(
                        "Tariff node selection attempt %s/3 failed; %.1f sn sonra yeniden: %s",
                        attempt,
                        backoff,
                        exc,
                    )
                    time.sleep(backoff)
            match = re.search(r"\{.*\}", response.text or "", re.DOTALL)
            data = json.loads(match.group(0) if match else (response.text or ""))
            # Şema sınırları BURADA uygulanmalı: CandidateSelection(**data) bunları
            # aşan listede ValidationError fırlatır ve seçimin tamamı düşerdi.
            # Aşağıdaki kırpma nesne kurulduktan sonra yapıldığı için hiç
            # çalışmıyordu; model 4'ten fazla alternatif döndürdüğünde karar
            # sessizce MANUAL_REVIEW'a gidiyordu. Modelin fazla üretmesi bir
            # sözleşme ihlali değil, normal bir sapmadır; kırpılır.
            data["alternative_candidate_ids"] = (data.get("alternative_candidate_ids") or [])[:4]
            data["reasoning_points"] = (data.get("reasoning_points") or [])[:6]
            data["applied_gir_keys"] = (data.get("applied_gir_keys") or [])[:10]
            data["cited_chapter_notes"] = [
                str(c).zfill(2) for c in (data.get("cited_chapter_notes") or [])
            ][:10]

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
                if (
                    any(al in full_reasoning_text for al in aliases)
                    and g_code not in data["applied_gir_keys"]
                    and len(data["applied_gir_keys"]) < 10
                ):
                    data["applied_gir_keys"].append(g_code)

            for ch_match in re.findall(r"fas[iı]l\s*(\d{1,2})", full_reasoning_text, re.IGNORECASE):
                ch_z = ch_match.zfill(2)
                if ch_z not in data["cited_chapter_notes"] and len(data["cited_chapter_notes"]) < 10:
                    data["cited_chapter_notes"].append(ch_z)

            selection = CandidateSelection(**data)
            valid_ids = set(option_map)
            if rejected_codes and selection.status == CandidateSelectionStatus.SELECT:
                picked = option_map.get(selection.selected_candidate_id) or {}
                picked_code = re.sub(r"\D", "", str(picked.get("gtip_code") or ""))
                if picked_code and picked_code in set(rejected_codes):
                    logger.warning(
                        "Model reddedilen dalı yeniden seçti (%s); seçim geçersiz.", picked_code
                    )
                    # Hak ve bütçe varsa bir kez daha sorulur; doğrudan pes etmek
                    # geri almanın kendisini boşa çıkarıyordu.
                    if _no_match_retries > 0 and (deadline is None or time.monotonic() < deadline):
                        return self.select_tariff_node(
                            raw_text,
                            level,
                            nodes,
                            _no_match_retries=_no_match_retries - 1,
                            precedents=precedents,
                            chapter_notes=chapter_notes,
                            narrowing=True,
                            rejected_codes=rejected_codes,
                            deadline=deadline,
                        )
                    return CandidateSelection(
                        status=CandidateSelectionStatus.NO_MATCH,
                        reasoning_points=[
                            "Model, daha önce eşleşme vermeyen dalı yeniden önerdi."
                        ],
                    )
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
            budget_left = deadline is None or time.monotonic() < deadline
            if should_retry_choice and _no_match_retries > 0 and budget_left:
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
                    rejected_codes=rejected_codes,
                    deadline=deadline,
                )
            return selection
        except Exception as exc:
            logger.error("Tariff node selection failed closed: %s", exc)
            return CandidateSelection(
                status=CandidateSelectionStatus.NO_MATCH,
                reasoning_points=["Model yanıtı kapalı seçenek sözleşmesine bağlanamadı."],
            )


llm_verifier = LLMFactVerifier()
