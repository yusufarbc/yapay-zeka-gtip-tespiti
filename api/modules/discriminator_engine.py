"""Erken tarife dalı ayrımı ve çoktan seçmeli HITL soruları.

Bu modül LLM kullanmaz. Aynı üst düğümde puanları birbirine yakın iki yasal
dalı bulur, açıklamalardaki ölçü/malzeme ayrımını çıkarır ve kullanıcı yanıtını
doğrudan kilitlenecek dala bağlar.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from pydantic import BaseModel, Field, model_validator


SCORE_DELTA_THRESHOLD = 0.08


class TariffBranch(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    description: str = Field(default="", max_length=4000)
    score: float = Field(ge=0.0, le=1.0)
    level: str = Field(default="HEADING", max_length=20)


class DiscriminatorQuestion(BaseModel):
    session_id: str
    parameter_name: str
    question_text: str
    options: List[str]
    target_branches: Dict[str, str]

    @model_validator(mode="after")
    def validate_option_mapping(self) -> "DiscriminatorQuestion":
        if len(self.options) < 3:
            raise ValueError("Ayırt edici soru en az iki dal ve 'Bilinmiyor' seçeneği içermelidir.")
        expected = {str(index) for index in range(len(self.options))}
        if set(self.target_branches) != expected:
            raise ValueError("Her seçenek tam olarak bir hedef dal eşlemesine sahip olmalıdır.")
        return self


class DiscriminatorExtractor:
    """Yakın skorlu iki dal arasındaki yasal ayrımı deterministik çıkarır."""

    _THRESHOLD = re.compile(
        r"(?P<operator>≤|>=|<=|>|<|en\s+(?:çok|az)|fazla(?:sı)?|geçmeyen)\s*"
        r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>w|watt|v|volt|kg|g|cm|mm|m|%)?",
        re.IGNORECASE,
    )
    _MATERIALS = (
        "pamuk", "yün", "ipek", "polyester", "plastik", "kauçuk", "deri",
        "çelik", "demir", "alüminyum", "bakır", "cam", "ahşap", "seramik",
    )

    def __init__(self, score_delta_threshold: float = SCORE_DELTA_THRESHOLD):
        self.score_delta_threshold = float(score_delta_threshold)

    @staticmethod
    def _coerce_branch(value: Any) -> TariffBranch:
        if isinstance(value, TariffBranch):
            return value
        if isinstance(value, Mapping):
            description = str(value.get("branch_context") or value.get("description") or "")
            return TariffBranch(
                code=str(value.get("code") or value.get("gtip_code") or ""),
                description=description,
                score=float(value.get("score", value.get("similarity_score", 0.0)) or 0.0),
                level=str(value.get("level") or "HEADING"),
            )
        return TariffBranch(
            code=str(getattr(value, "code", None) or getattr(value, "gtip_code", "")),
            description=str(getattr(value, "description", "")),
            score=float(getattr(value, "score", 0.0) or 0.0),
            level=str(getattr(value, "level", "HEADING")),
        )

    def competing_branches(self, branches: Sequence[Any]) -> List[TariffBranch]:
        ranked = sorted((self._coerce_branch(item) for item in branches), key=lambda item: item.score, reverse=True)
        if len(ranked) < 2:
            return []
        top, runner_up = ranked[:2]
        if top.code == runner_up.code or top.score - runner_up.score >= self.score_delta_threshold:
            return []
        return [top, runner_up]

    def extract(
        self,
        session_id: str,
        branches: Sequence[Any],
        rule_hints: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> Optional[DiscriminatorQuestion]:
        competing = self.competing_branches(branches)
        if not competing:
            return None

        first, second = competing
        hint = next(iter(rule_hints or []), None)
        if hint:
            parameter = str(hint.get("parameter_name") or hint.get("parametre_adi") or "tarife_kriteri")
            question = str(hint.get("question_text") or hint.get("soru_metni") or "").strip()
        else:
            parameter, question = self._infer_criterion(first, second)

        if not question:
            question = "Ürün aşağıdaki resmi tarife tanımlarından hangisini karşılıyor?"

        return DiscriminatorQuestion(
            session_id=session_id,
            parameter_name=parameter,
            question_text=question,
            options=[
                f"{first.code} — {first.description[:420]}",
                f"{second.code} — {second.description[:420]}",
                "Bilinmiyor",
            ],
            target_branches={"0": first.code, "1": second.code, "2": ""},
        )

    def _infer_criterion(self, first: TariffBranch, second: TariffBranch) -> tuple[str, str]:
        first_text = first.description.lower()
        second_text = second.description.lower()
        combined = f"{first_text} {second_text}"
        threshold = self._THRESHOLD.search(combined)
        if threshold:
            value = threshold.group("value").replace(",", ".")
            unit = (threshold.group("unit") or "").lower()
            names = {
                "w": "motor_gucu_watt", "watt": "motor_gucu_watt",
                "v": "gerilim_volt", "volt": "gerilim_volt",
                "%": "malzeme_orani_yuzde", "kg": "agirlik_kg", "g": "agirlik_gram",
                "cm": "uzunluk_cm", "mm": "uzunluk_mm", "m": "uzunluk_metre",
            }
            parameter = names.get(unit, "olcu_esigi")
            label = f" {unit}" if unit else ""
            return parameter, f"Ürünün ilgili teknik değeri {value}{label} eşiğinin hangi tarafındadır?"

        upholstered_terms = ("döşemeli", "dolgulu", "içleri doldurulmuş", "kaplanmış")
        negative_upholstery_terms = ("döşemeli olmayan", "doldurulmamış", "kaplanmamış")

        def is_upholstered(text: str) -> bool:
            if any(term in text for term in negative_upholstery_terms):
                return False
            return any(term in text for term in upholstered_terms)

        first_upholstered = is_upholstered(first_text)
        second_upholstered = is_upholstered(second_text)
        if first_upholstered != second_upholstered:
            return "dosemeli_mi", "Sandalye/koltuğun oturma veya sırt bölümü dolgu ya da kumaş/deri ile döşenmiş midir?"

        materials = [
            material for material in self._MATERIALS
            if (material in first_text) != (material in second_text)
        ]
        if materials:
            material = materials[0]
            return f"{material}_orani", f"Ürünün baskın malzemesi veya ağırlıkça ana bileşeni {material} mudur?"

        return "tarife_dali", "Ürün aşağıdaki resmi tarife tanımlarından hangisini karşılıyor?"


discriminator_extractor = DiscriminatorExtractor()
