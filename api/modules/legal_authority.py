"""Deterministik hukuk hiyerarşisi ve yürürlük kapısı.

Bu modül benzerlik skorunun hukuki otoriteyi geçmesini engeller. LLM yalnızca
bu kapıdan geçen, aktif TGTC yaprağına bağlı kapalı aday kümesini değerlendirebilir.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, List, Tuple

from api.schemas.product import GTIPCandidate, LegalSource


NORMATIVE_SOURCE_TYPES = {"TGTC_2026", "TGTC", "GIR", "GYK", "FASIL_NOTU", "SECTION_NOTE"}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        # Tarihi çözülemeyen bir kaynağı otomatik karar dayanağı yapma.
        return None


def is_effective(source: LegalSource, as_of: date | None = None) -> bool:
    """Yürürlük bilgisi varsa kaynağın karar tarihinde aktif olduğunu denetler."""
    as_of = as_of or date.today()
    start = _parse_date(source.effective_from)
    end = _parse_date(source.effective_to)
    return not ((start and start > as_of) or (end and end < as_of))


def sort_by_authority(sources: Iterable[LegalSource]) -> List[LegalSource]:
    """Kanıtı normatif kaynaklardan emsale doğru kararlı biçimde sıralar."""
    return sorted(
        sources,
        key=lambda source: (
            source.authority_level,
            0 if source.legal_role == "NORMATIVE" else 1,
            source.reference_no,
        ),
    )


def validate_candidate_evidence(
    candidate: GTIPCandidate, as_of: date | None = None
) -> Tuple[bool, str, List[LegalSource]]:
    """Adayın aktif normatif TGTC dayanağı olmadan otomatik karar almasını engeller."""
    ordered = sort_by_authority(candidate.legal_sources)
    normative = [
        source for source in ordered
        if source.source_type in NORMATIVE_SOURCE_TYPES and source.legal_role == "NORMATIVE"
    ]
    if not normative:
        return False, "MISSING_NORMATIVE_EVIDENCE", ordered
    has_tgtc = any(source.source_type in {"TGTC_2026", "TGTC"} for source in normative)
    has_gir = any(source.source_type in {"GIR", "GYK"} for source in normative)
    if not has_tgtc or not has_gir:
        return False, "MISSING_NORMATIVE_EVIDENCE", ordered
    has_active_tgtc = any(
        source.source_type in {"TGTC_2026", "TGTC"} and is_effective(source, as_of)
        for source in normative
    )
    has_active_gir = any(
        source.source_type in {"GIR", "GYK"} and is_effective(source, as_of)
        for source in normative
    )
    if not has_active_tgtc or not has_active_gir:
        return False, "EXPIRED_EVIDENCE", ordered
    return True, "PASSED", ordered
