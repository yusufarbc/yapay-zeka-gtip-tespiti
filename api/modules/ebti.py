"""Retrieve EU EBTI decisions as non-binding CN8 evidence for Turkish classification."""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from datetime import date
from typing import Optional

from sqlalchemy import or_

from api.config import settings
from api.db.database import EbtiKarariModel, SessionLocal
from api.schemas.product import PrecedentEBTI

logger = logging.getLogger(__name__)


def digits(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    return {word for word in re.findall(r"[a-z0-9]{3,}", normalized) if len(word) > 2}


def _usable(row: EbtiKarariModel) -> bool:
    today = date.today().isoformat()
    return (
        row.durum == "VALID"
        and bool(row.gecerlilik_bitis)
        and row.karar_tarihi <= today <= row.gecerlilik_bitis
        and len(digits(row.cn_kodu_8hane)) == 8
    )


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    magnitude = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    return max(0.0, sum(x * y for x, y in zip(left, right)) / magnitude) if magnitude else 0.0


def search_ebti(product_text: str, *, cn8: Optional[str] = None, limit: int = 5) -> list[PrecedentEBTI]:
    """Find valid decisions. Semantic matches require the dedicated multilingual model."""
    query_terms = sorted(tokens(product_text), key=len, reverse=True)[:6]
    if not query_terms:
        return []
    try:
        with SessionLocal() as session:
            base = session.query(EbtiKarariModel).filter(EbtiKarariModel.durum == "VALID")
            if cn8:
                clean_cn = digits(cn8)
                if len(clean_cn) != 8:
                    return []
                base = base.filter(EbtiKarariModel.cn_kodu_8hane == clean_cn)
            if not session.query(base.exists()).scalar():
                return []

            query_vector = None
            if not settings.USE_GCP_EMULATOR:
                try:
                    from api.modules.vertex_client import generate_embedding
                    vector = generate_embedding(product_text, model=settings.EBTI_EMBEDDING_MODEL)
                    if len(vector) == 768 and any(vector):
                        query_vector = vector
                except Exception as exc:
                    logger.warning("EBTI multilingual embedding unavailable: %s", exc)

            candidates = []
            if query_vector is not None and session.bind.dialect.name == "postgresql":
                distance = EbtiKarariModel.embedding.cosine_distance(query_vector)
                candidates.extend(
                    base.filter(EbtiKarariModel.embedding_model == settings.EBTI_EMBEDDING_MODEL)
                    .filter(EbtiKarariModel.embedding.isnot(None))
                    .order_by(distance).limit(60).all()
                )
            elif query_vector is not None:
                candidates.extend(base.filter(EbtiKarariModel.embedding.isnot(None)).limit(500).all())
            if query_terms:
                clauses = [EbtiKarariModel.urun_tanimi.ilike(f"%{term}%") for term in query_terms]
                candidates.extend(base.filter(or_(*clauses)).limit(100).all())
            if cn8 and not candidates:
                candidates = base.limit(100).all()

            query_tokens = tokens(product_text)
            matches = []
            seen = set()
            for row in candidates:
                if row.id in seen or not _usable(row):
                    continue
                seen.add(row.id)
                description_tokens = tokens(row.urun_tanimi)
                overlap = len(query_tokens & description_tokens)
                lexical = overlap / max(1, len(query_tokens))
                semantic = (
                    _cosine(query_vector, list(row.embedding))
                    if query_vector is not None and row.embedding is not None
                    and row.embedding_model == settings.EBTI_EMBEDDING_MODEL
                    else 0.0
                )
                similarity = max(lexical, semantic)
                if similarity < 0.35:
                    continue
                matches.append(PrecedentEBTI(
                    reference_no=row.referans_no,
                    country=row.kaynak_ulke,
                    cn_code=row.cn_kodu_8hane,
                    issue_date=row.karar_tarihi,
                    valid_until=row.gecerlilik_bitis,
                    product_description=row.urun_tanimi,
                    legal_justification=row.karar_gerekcesi,
                    language=row.dil,
                    similarity_score=round(min(1.0, similarity), 4),
                    source_url=row.kaynak_url,
                    image_url=row.gorsel_url,
                ))
            return sorted(matches, key=lambda item: item.similarity_score, reverse=True)[:limit]
    except Exception as exc:
        logger.warning("EBTI search unavailable: %s", exc)
        return []


def translate_justifications(items: list[PrecedentEBTI]) -> list[PrecedentEBTI]:
    """Translate only evidence shown to the adviser; preserve the original text."""
    if not items or settings.USE_GCP_EMULATOR:
        return items
    try:
        from api.modules.vertex_client import get_genai_client
        for item in items:
            if not item.legal_justification or item.language.lower().startswith("tr"):
                continue
            response = get_genai_client().models.generate_content(
                model=settings.FAST_LLM_MODEL,
                contents=(
                    "Translate this EU customs classification reasoning into Turkish faithfully. "
                    "Do not add legal conclusions or codes. Return only the translation.\n"
                    f"{item.legal_justification[:4000]}"
                ),
            )
            item.legal_justification_tr = (response.text or "").strip() or None
    except Exception as exc:
        logger.warning("EBTI translation unavailable: %s", exc)
    return items
