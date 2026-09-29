"""Sınıflandırmadan önce ürün profili: eşya ne, ne işe yarar, hangi parçası neyden yapılmış.

Müşavir geri bildirimi: "cam balkon sistemi" yazıldığında sistem alüminyumdan hiç
bahsetmiyordu. Model bu tür ürünlerde taşıyıcının tipik olarak alüminyum olduğunu
bilir, fakat bu bir VARSAYIMDIR. Profil her bilginin kaynağını taşır; tahmin
edilen bir parça malzemesi kullanıcıya tek soruyla sorulur.

Profil yalnız OLGU toplar (parça -> malzeme, kaynağıyla). Esas niteliği hangi
malzemenin verdiği bir tarife hükmüdür (GYK 3(b)); fasıl notlarını ve emsalleri
gören sınıflandırıcıya bırakılır. İlk denemede profilden bu hüküm istenince model
cam balkonun esasını "temperli cam" sandı ve teyit seçeneklerinde alüminyum hiç
yer almadı.

Teyit kararı modelde değil sunucuda, deterministiktir (`confirmation_question`).
Kaynaklar da sunucuda doğrulanır (`_verify_sources`).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set

from api.config import settings
from api.modules.evidence_pool import EvidencePool
from api.schemas.dossier import MaterialFact, ProductDossier, ProductProfile, ProfileFact
from api.schemas.product import ProductFeatures

logger = logging.getLogger("ProductProfile")

UNKNOWN_OPTION = "Bilinmiyor"


# ──────────────────────────────────────────────────────────────────────────────
# Metin eşleştirme (kaynak doğrulaması)
# ──────────────────────────────────────────────────────────────────────────────

def _fold(text: Any) -> str:
    value = str(text or "").replace("ı", "i").replace("İ", "I")
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch)).lower()


def _stems(text: Any, min_len: int = 3) -> Set[str]:
    """Türkçe eklemeli yapı için ilk 5 karakter kökü ("alüminyumdan" ~ "aluminyum")."""
    return {word[:5] for word in re.findall(r"[a-z]+", _fold(text)) if len(word) >= min_len}


def _coverage(value: str, source_text: str) -> float:
    """Bilginin kelimelerinin kaçta kaçı kaynak metinde geçiyor (0-1)."""
    value_stems = _stems(value)
    if not value_stems:
        return 0.0
    return len(value_stems & _stems(source_text)) / len(value_stems)


def _appears_in(value: str, source_text: str) -> bool:
    """Bilgi kaynak metinde gerçekten söylenmiş mi?

    Tek ortak kelime yetmez: canlıda modelin tahmin ettiği "balkonları dış
    etkenlerden korumak…" cümlesi, kullanıcı yalnız "cam balkon sistemi" yazdığı
    halde "balkon" kelimesi yüzünden "beyan" sayıldı. Kelimelerin çoğu (en az
    %60) metinde geçmelidir; tek kelimelik malzeme adları için bu tam eşleşmedir.
    """
    return _coverage(value, source_text) >= 0.6


def _verify_sources(profile: ProductProfile, user_text: str, pool: Optional[EvidencePool]) -> ProductProfile:
    """Kaynakları delille eşitler.

    - Model tahmini "kullanıcı beyanı" diye işaretlerse ekranda ve promptta beyan
      gibi görünür, teyit sorusu da sorulmaz: kullanıcı metninde geçmeyen USER
      bilgisi varsayıma (INFERRED) indirilir. Doküman/fotoğraf kaynağı ancak
      gerçekten ek varsa kabul edilir.
    - Tersine, kullanıcının açıkça yazdığı bilgi varsayım diye işaretlenmişse
      beyana yükseltilir; aksi halde kullanıcıya kendi yazdığı sorulurdu
      ("alüminyum doğrama cam balkon" -> "çerçeve hangi malzemeden?").
    """
    has_attachments = bool(pool and pool.attachments)

    def check(fact: Optional[ProfileFact]) -> None:
        if fact is None:
            return
        if fact.source == "USER" and not _appears_in(fact.value, user_text):
            fact.source = "INFERRED"
        elif fact.source in {"DOCUMENT", "IMAGE"} and not has_attachments:
            fact.source = "INFERRED"
        elif fact.source == "INFERRED" and _appears_in(fact.value, user_text):
            fact.source = "USER"

    for fact in (profile.product_type, profile.function, profile.use_place, *profile.materials):
        check(fact)
    return profile


# ──────────────────────────────────────────────────────────────────────────────
# Profil çıkarımı
# ──────────────────────────────────────────────────────────────────────────────

_PROMPT = """Sen gümrük sınıflandırması öncesi ürün tanımlama uzmanısın. GTİP veya tarife kodu YAZMA ve
tarife hükmü (hangi fasıl, esas nitelik) VERME. Görevin yalnız OLGULARI toplamak: eşya ne, ne işe yarar,
nerede kullanılır, makine/cihaz mı, hangi parçası hangi malzemeden yapılmış.

KAYNAK KURALI — her bilgi için "source" alanını dürüstçe doldur:
- USER: kullanıcı beyanında açıkça yazıyor.
- DOCUMENT: yüklenen katalog, broşür veya teknik resimde görülüyor.
- IMAGE: ürün fotoğrafında görülüyor.
- INFERRED: hiçbir delilde yok; bu tür ürünlerde tipik olduğu için tahmin ediyorsun.
Tahmin yapmalısın, ama tahmini ASLA USER/DOCUMENT/IMAGE diye işaretleme.

MAKİNE/CİHAZ: Makine, mekanik veya elektrikli cihaz, elektronik alet, bunların modülleri ve aksam-parçaları
için is_machine=true. Bu eşyalarda malzeme sınıflandırmayı çoğu zaman belirlemez; materials boş kalabilir.

MALZEME (makine/cihaz değilse): Eşyayı oluşturan ana parçaları ayrı ayrı yaz (ör. taşıyıcı çerçeve/profil,
panel, gövde, kaplama, dolgu). Her parça için malzemeyi ve kaynağını ver. Bir parçanın malzemesi INFERRED ise
"alternatives" alanına bu parça için yaygın DİĞER malzemeleri yaz (en çok 3). Kullanıcı beyanında geçen
parçayı atlama; beyanda geçmeyen ama bu tür üründe bulunan parçayı da ekle. "main_part": parça eşyanın
gövdesini, taşıyıcı yapısını veya hacminin/ağırlığının büyük kısmını oluşturuyorsa true; bağlantı elemanı,
conta, vida, bağcık, etiket gibi yardımcı parçalar için false.

product_type_alternatives: eşyanın NE OLDUĞU delillerden anlaşılmıyorsa (yalnız ticari kod, marka, model
numarası vb.) olası eşya türleri (en çok 3). Eşya açıkça adlandırılmışsa boş bırak.

{evidence}
Yalnız şu JSON'u döndür:
{{"product_type":{{"value":"eşyanın ne olduğu","source":"USER","evidence":"kısa alıntı"}},
"function":{{"value":"ne işe yarar","source":"INFERRED","evidence":"..."}},
"use_place":{{"value":"nerede kullanılır","source":"INFERRED","evidence":"..."}},
"is_machine":false,
"materials":[{{"part":"taşıyıcı çerçeve","value":"...","source":"INFERRED","main_part":true,"alternatives":["...","..."],"evidence":"..."}},
{{"part":"panel","value":"...","source":"USER","main_part":true,"alternatives":[],"evidence":"..."}}],
"product_type_alternatives":[],
"summary":"1-2 cümle"}}"""


def _evidence_block(user_text: str, pool: Optional[EvidencePool]) -> str:
    parts = [f"<kullanici_beyani>\n{user_text}\n</kullanici_beyani>"]
    if pool and pool.attachments:
        kinds = ", ".join("doküman (PDF)" if mime == "application/pdf" else "görsel" for _, mime in pool.attachments)
        parts.append(f"Ekli dosyalar: {kinds}. Görseller ürün fotoğrafı (IMAGE) veya teknik resim/katalog (DOCUMENT) olabilir.")
    return "DELİLLER:\n" + "\n".join(parts) + "\n"


def _call_model(user_text: str, pool: Optional[EvidencePool]) -> Dict[str, Any]:
    from google.genai import types

    from api.modules.vertex_client import get_genai_client

    contents: List[Any] = [_PROMPT.format(evidence=_evidence_block(user_text, pool))]
    for uri, mime in (pool.attachments if pool else []):
        contents.append(types.Part.from_uri(file_uri=uri, mime_type=mime))
    last_error: Optional[Exception] = None
    for attempt in range(2):
        try:
            response = get_genai_client().models.generate_content(
                model=settings.PROFILE_LLM_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    temperature=0.0,
                    response_mime_type="application/json",
                    http_options=types.HttpOptions(timeout=settings.PROFILE_TIMEOUT_MS),
                ),
            )
            match = re.search(r"\{.*\}", response.text or "", re.DOTALL)
            return json.loads(match.group(0) if match else (response.text or "{}"))
        except Exception as exc:  # 429/504 geçicidir; bir kez yeniden denenir
            last_error = exc
            logger.warning("Profil çağrısı denemesi %s/2 başarısız: %s", attempt + 1, exc)
    raise last_error  # type: ignore[misc]


def _fact(raw: Any, cls=ProfileFact) -> Optional[ProfileFact]:
    if not isinstance(raw, dict) or not str(raw.get("value") or "").strip():
        return None
    source = str(raw.get("source") or "INFERRED").upper()
    if source not in {"USER", "DOCUMENT", "IMAGE", "INFERRED"}:
        source = "INFERRED"
    data: Dict[str, Any] = {
        "value": str(raw["value"]).strip()[:500],
        "source": source,
        "evidence": (str(raw.get("evidence")).strip()[:500] if raw.get("evidence") else None),
    }
    if cls is MaterialFact:
        data["part"] = (str(raw.get("part")).strip()[:200] if raw.get("part") else None)
        data["main_part"] = raw.get("main_part") is not False
        data["alternatives"] = [
            alt for alt in _strings(raw.get("alternatives"), 3) if _fold(alt) != _fold(data["value"])
        ]
    return cls(**data)


def _strings(raw: Any, limit: int) -> List[str]:
    if not isinstance(raw, list):
        return []
    seen, result = set(), []
    for item in raw:
        text = str(item or "").strip()[:100]
        if text and _fold(text) not in seen:
            seen.add(_fold(text))
            result.append(text)
    return result[:limit]


def _from_model_data(data: Dict[str, Any], fallback_name: str) -> ProductProfile:
    product_type = _fact(data.get("product_type")) or ProfileFact(value=fallback_name, source="USER")
    materials = [m for m in (_fact(item, MaterialFact) for item in (data.get("materials") or [])[:8]) if m]
    return ProductProfile(
        product_type=product_type,
        function=_fact(data.get("function")),
        use_place=_fact(data.get("use_place")),
        is_machine=bool(data.get("is_machine")),
        materials=materials,
        product_type_alternatives=_strings(data.get("product_type_alternatives"), 3),
        summary=(str(data.get("summary")).strip()[:800] if data.get("summary") else None),
    )


def _deterministic_profile(user_text: str, dossier: Optional[ProductDossier]) -> ProductProfile:
    """Model çağrılmadan kurulan profil: yalnız kullanıcının söyledikleri (hepsi USER).

    İki durumda kullanılır: kullanıcı ad, işlev ve malzemeyi zaten vermişse
    (tahmine gerek yok) ve model kullanılamadığında (test/emülatör, hata).
    """
    from api.modules.feature_extractor import feature_extractor

    if dossier:
        material_text = None if dossier.is_machine else dossier.material
        materials = [MaterialFact(value=material_text, source="USER")] if material_text else []
        return ProductProfile(
            product_type=ProfileFact(value=dossier.product_name, source="USER"),
            function=ProfileFact(value=dossier.use_and_function, source="USER") if dossier.use_and_function else None,
            is_machine=dossier.is_machine,
            materials=materials,
        )

    first_line = next((line.strip() for line in user_text.splitlines() if line.strip()), user_text.strip())
    material = feature_extractor._extract_explicit_material(user_text.lower())
    materials = [] if material == "Belirtilmedi" else [MaterialFact(value=material, source="USER")]
    return ProductProfile(
        product_type=ProfileFact(value=first_line[:300] or "Belirtilmemiş eşya", source="USER"),
        materials=materials,
    )


def build_profile(
    user_text: str,
    dossier: Optional[ProductDossier] = None,
    pool: Optional[EvidencePool] = None,
) -> ProductProfile:
    notes = list(pool.notes) if pool else []

    complete_declaration = bool(
        dossier and dossier.use_and_function and (dossier.is_machine or dossier.material)
        and not dossier.has_evidence_attachments()
    )
    if complete_declaration or settings.USE_GCP_EMULATOR or settings.ENVIRONMENT == "testing":
        profile = _deterministic_profile(user_text, dossier)
    else:
        try:
            fallback_name = dossier.product_name if dossier else user_text[:300]
            profile = _from_model_data(_call_model(user_text, pool), fallback_name=fallback_name)
            profile = _verify_sources(profile, user_text, pool)
        except Exception as exc:
            logger.warning("Ürün profili çıkarılamadı; yalnız beyan kullanılıyor: %s", exc)
            profile = _deterministic_profile(user_text, dossier)
            notes.append("Ürün profili model tarafından çıkarılamadı; yalnız kullanıcı beyanı kullanıldı.")

    # Formdaki malzeme alanı açık beyandır: modelin tahminlerinin önüne geçer ve
    # kullanıcıya ayrıca malzeme sorulmaz.
    if dossier and dossier.material and not dossier.is_machine:
        declared = MaterialFact(value=dossier.material, source="USER")
        profile.materials = [declared] + [
            m for m in profile.materials if m.source != "INFERRED" and not _appears_in(m.value, dossier.material)
        ]
    if dossier and dossier.is_machine:
        profile.is_machine = True
    profile.essential_material = _primary_material(profile)
    profile.evidence_notes = notes
    return profile


def _primary_material(profile: ProductProfile) -> Optional[MaterialFact]:
    """Özet için ilk malzeme: önce beyan/teyit edilmiş olan. Tarife hükmü değildir."""
    confirmed = [m for m in profile.materials if m.source != "INFERRED"]
    return (confirmed or profile.materials or [None])[0]


# ──────────────────────────────────────────────────────────────────────────────
# Teyit sorusu
# ──────────────────────────────────────────────────────────────────────────────

def _material_key(fact: MaterialFact) -> str:
    return f"material:{_fold(fact.part or '')}"


def confirmation_question(profile: ProductProfile, skip: Optional[Set[str]] = None) -> Optional[Dict[str, Any]]:
    """Kararı etkileyen bilgi yalnız varsayıma dayanıyorsa sorulacak TEK soru.

    - Eşyanın ne olduğu delillerden anlaşılmıyorsa (ör. yalnız ticari kod) önce o sorulur.
    - Makine/cihaz değilse, malzemesi tahmin edilen ilk ANA parça sorulur. Yardımcı
      parçalar (conta, bağlantı elemanı) sorulmaz ve bir analizde en çok bir malzeme
      sorusu sorulur: her parçayı tek tek sormak kullanıcıyı yorar.
    İşlev tahmini soru üretmez: eşya adlandırılmışsa işlev çoğu zaman adından çıkar
    ve her analizde soru sormak kullanıcıyı yorar.
    """
    skip = skip or set()
    if (
        "product_type" not in skip
        and profile.product_type.source == "INFERRED"
        and profile.product_type_alternatives
    ):
        values = _dedupe([profile.product_type.value, *profile.product_type_alternatives])[:4]
        return {
            "attribute": "product_type",
            "key": "product_type",
            "question_text": "Bu ürün nedir? Delillerden eşyanın türü kesin anlaşılamadı.",
            "values": values,
            "inferred_value": profile.product_type.value,
        }

    if profile.is_machine or any(key.startswith("material:") for key in skip):
        return None
    for fact in profile.materials:
        if fact.source != "INFERRED" or not fact.main_part:
            continue
        values = _dedupe([fact.value, *fact.alternatives])[:4]
        if len(values) < 2:
            continue
        part = fact.part or "ürün"
        return {
            "attribute": "material",
            "key": _material_key(fact),
            "question_text": (
                f"{profile.product_type.value}: {part} hangi malzemeden yapılmış? "
                f"Belirtilmediği için '{fact.value}' varsayıldı."
            ),
            "values": values,
            "inferred_value": fact.value,
            "part": fact.part,
        }
    return None


def _dedupe(values: List[str]) -> List[str]:
    seen, result = set(), []
    for value in values:
        key = _fold(value).strip()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def apply_answer(profile: ProductProfile, attribute: str, value: str, part: Optional[str] = None) -> bool:
    """Müşavirin yanıtını profile işler. Yanıt "Bilinmiyor" ise False döner (teyit edilmedi)."""
    if not value:
        return False
    if attribute == "material":
        confirmed = MaterialFact(value=value, source="BROKER", part=part)
        replaced = False
        for index, fact in enumerate(profile.materials):
            if _fold(fact.part or "") == _fold(part or "") and fact.source == "INFERRED":
                profile.materials[index] = confirmed
                replaced = True
                break
        if not replaced:
            profile.materials.insert(0, confirmed)
        profile.essential_material = _primary_material(profile)
    elif attribute == "product_type":
        profile.product_type = ProfileFact(value=value, source="BROKER")
        profile.product_type_alternatives = []
    return True


def has_unconfirmed_decisive_fact(profile: ProductProfile) -> bool:
    """Karar, teyit edilmemiş bir varsayıma mı dayanıyor? (müşavir inceleme işareti)"""
    if profile.product_type.source == "INFERRED":
        return True
    return not profile.is_machine and any(m.source == "INFERRED" and m.main_part for m in profile.materials)


# ──────────────────────────────────────────────────────────────────────────────
# Mevcut hatla uyum
# ──────────────────────────────────────────────────────────────────────────────

def profile_to_features(profile: ProductProfile, raw_text: str) -> ProductFeatures:
    """Dolaşımın ve oturum durumunun kullandığı eski ProductFeatures biçimi."""
    from api.modules.feature_extractor import regex_specs

    specs, composition = regex_specs(raw_text.lower())
    if profile.is_machine:
        material = "makine/cihaz"
    else:
        material = " / ".join(dict.fromkeys(m.value for m in profile.materials)) or "Belirtilmedi"
    function = profile.function.value if profile.function else None
    return ProductFeatures(
        product_name=profile.product_type.value[:2000],
        commercial_name=profile.product_type.value[:1000],
        primary_material=material[:500],
        function=(function or profile.product_type.value)[:1000],
        composition_percentages=composition,
        intended_use=((profile.use_place.value if profile.use_place else None) or function or profile.product_type.value)[:1000],
        # Birden çok malzeme bileşik eşya demektir, takım (set) değil.
        is_set_or_kit=bool(re.search(r"\b(set|takım|takim|kit)\b", _fold(raw_text))),
        is_disassembled=bool(re.search(r"\b(demonte|sokulmus|parca halinde)\b", _fold(raw_text))),
        technical_specifications=specs,
    )
