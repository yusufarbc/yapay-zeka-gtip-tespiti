"""Closed-set traversal of the official 2026 TGTC catalog.

The model never creates a tariff code. At each level it returns an opaque
option id; this module resolves that id to a server-owned chapter, heading,
subheading or 12-digit leaf. The workflow performs the final active-leaf check.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import or_

from api.config import settings
from api.db.database import (
    SessionLocal,
    EbtiKararModel,
    GumrukEmsalKararModel,
    TariffHierarchyModel,
    TgtcGtipModel,
    _load_subheading_contexts,
    validate_leaf_gtip,
)
from api.db.tgtc_knowledge_base import get_local_tgtc_headings, load_tgtc_chapters
from api.modules.discriminator_engine import DiscriminatorQuestion
from api.modules.llm_verifier import llm_verifier
from api.schemas.predicate import CandidateSelection, CandidateSelectionStatus
from api.schemas.product import GTIPCandidate, LegalSource, PrecedentBTB, ProductFeatures


logger = logging.getLogger("ClosedSetTariffSelector")


@dataclass
class HierarchicalSearchResult:
    candidates: List[GTIPCandidate] = field(default_factory=list)
    discriminator_question: Optional[DiscriminatorQuestion] = None
    traversal_state: Dict[str, Any] = field(default_factory=dict)


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _description(node: Dict[str, Any]) -> str:
    return str(node.get("branch_context") or node.get("description") or "").strip()


def _normalize_product_text(value: Any) -> str:
    text = str(value or "").replace("ı", "i").replace("İ", "I")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _shorten_siblings(nodes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Kardeş seçeneklerin paylaştığı ortak yol önekini atar.

    Açıklamalar artık kökten yaprağa tam yol taşıyor. Aynı ebeveynin altındaki
    seçeneklerde bu yolun baş kısmı birebir aynıdır: seçimi belirleyen bilgi
    değil, yalnız tekrar. Hem modelin promptunda hem müşavire sorulan soruda
    ayrımı gömüyor ve seviye başına yüzlerce token harcıyordu.

    Yalnız TAMAMEN ortak olan seviyeler atılır; ayrım başlar başlamaz durulur.
    Tek seçenek varsa dokunulmaz (karşılaştıracak kardeş yoktur).
    """
    if len(nodes) < 2:
        return list(nodes)

    paths = [_description(node).split(" > ") for node in nodes]
    if any(len(path) < 2 for path in paths):
        return list(nodes)

    shared = 0
    while (
        all(len(path) > shared + 1 for path in paths)
        and len({path[shared].strip().casefold() for path in paths}) == 1
    ):
        shared += 1
    if not shared:
        return list(nodes)

    trimmed = []
    for node, path in zip(nodes, paths):
        trimmed.append({**node, "branch_context": " > ".join(path[shared:])})
    return trimmed


def _formatted_code(value: Any) -> str:
    code = _digits(value)
    if len(code) == 12:
        return f"{code[:4]}.{code[4:6]}.{code[6:8]}.{code[8:10]}.{code[10:12]}"
    return code


class RAGEngine:
    """Thin catalog adapter retained under the old name for API compatibility."""

    @staticmethod
    def _product_text(features: ProductFeatures, raw_text: str = "") -> str:
        # Özellik çıkarıcı ham metni dokuz alana damıtır ve gerisini atar; ölçü,
        # kullanım koşulu veya kompozisyon detayı gibi ayrımlar tarife seçimine
        # hiç ulaşmıyordu. Orijinal beyan en başta korunur.
        parts = [
            f"ORİJİNAL BEYAN: {raw_text}".strip() if str(raw_text or "").strip() else "",
            features.product_name,
            features.commercial_name,
            features.primary_material,
            features.function,
            features.intended_use,
            features.accessories_or_packaging,
            " ".join(
                f"{key}: {value}"
                for key, value in (features.technical_specifications or {}).items()
            ),
        ]
        return "\n".join(str(part).strip() for part in parts if part and str(part).strip())

    @staticmethod
    def search_btb_precedents(
        product_text: str,
        top_k: int = 5,
        exclude_refs: Optional[Set[str]] = None,
    ) -> List[PrecedentBTB]:
        """Search real BTB rows without mixing tariff-catalog pseudo records.

        `exclude_refs` yalnız değerlendirme içindir: benchmark numunesinin kendi BTB
        kaydı emsal olarak geri gelirse `exact_btb_candidate` birebir eşleşme verir
        ve ölçüm anlamsızlaşır. Üretim yolunda daima None'dır.
        """
        normalized_query = _normalize_product_text(product_text)
        raw_terms = [
            term
            for term in re.findall(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]+", str(product_text or ""))
            if len(term) >= 3
        ]
        if not normalized_query or not raw_terms:
            return []

        try:
            with SessionLocal() as session:
                clauses = [
                    GumrukEmsalKararModel.esya_tanimi.ilike(f"%{term}%")
                    for term in sorted(set(raw_terms), key=len, reverse=True)[:6]
                ]
                rows = session.query(
                    GumrukEmsalKararModel.referans_no,
                    GumrukEmsalKararModel.gtip_kodu,
                    GumrukEmsalKararModel.yayin_tarihi,
                    GumrukEmsalKararModel.esya_tanimi,
                    GumrukEmsalKararModel.hukuki_gerekce,
                    GumrukEmsalKararModel.kaynak_url,
                    GumrukEmsalKararModel.valid_until,
                ).filter(
                    GumrukEmsalKararModel.karar_tipi == "BTB",
                    or_(*clauses),
                )
                if exclude_refs:
                    rows = rows.filter(
                        GumrukEmsalKararModel.referans_no.notin_(list(exclude_refs))
                    )
                rows = rows.order_by(
                    GumrukEmsalKararModel.yayin_tarihi.desc()
                ).limit(200).all()
        except Exception as exc:
            logger.warning("BTB precedent search could not be completed: %s", exc)
            return []

        query_tokens = set(normalized_query.split())
        today = date.today().isoformat()
        matches: List[PrecedentBTB] = []
        seen = set()
        for ref_no, gtip, issue_date, description, legal, source_url, valid_until in rows:
            code = _digits(gtip)
            desc_normalized = _normalize_product_text(description)
            if len(code) != 12 or not desc_normalized:
                continue
            if valid_until and str(valid_until) != "9999-12-31" and str(valid_until) < today:
                continue
            key = (str(ref_no or ""), code)
            if key in seen:
                continue
            seen.add(key)
            description_tokens = set(desc_normalized.split())
            overlap = len(query_tokens & description_tokens)
            coverage = overlap / max(1, len(query_tokens))
            precision = overlap / max(1, len(description_tokens))
            if normalized_query == desc_normalized:
                score = 1.0
            elif normalized_query in desc_normalized or desc_normalized in normalized_query:
                score = 0.96
            else:
                score = 0.7 * coverage + 0.3 * precision
            if score < 0.30:
                continue
            matches.append(PrecedentBTB(
                btb_no=str(ref_no or "EMSAL-BTB"),
                gtip_code=_formatted_code(code),
                issue_date=str(issue_date or ""),
                product_description=str(description or ""),
                legal_justification=str(legal or ""),
                similarity_score=round(min(1.0, score), 4),
                source_type="BTB",
                source_url=str(source_url) if source_url else None,
            ))
        return sorted(matches, key=lambda item: item.similarity_score, reverse=True)[:top_k]

    @staticmethod
    def search_ebti_precedents(product_text: str, top_k: int = 3) -> List:
        """
        AB EBTI (European Binding Tariff Information) kararlarında emsal arar.

        'ebti_kararlari' tablosunda token overlap benzerliği hesaplanır.
        CN-8 kodu, Türk GTİP'inin ilk 8 hanesiyle eşleşen kararlar öne alınır.
        Sonuçlar PrecedentEBTI listesi olarak döner.

        Ağırlık: Hibrit RAG formülünde 0.30 katsayısı ile kullanılır.
        (Toplam: 0.50 × TR-BTB + 0.30 × EU-EBTI + 0.20 × TGTC)
        """
        from api.schemas.product import PrecedentEBTI

        normalized_query = _normalize_product_text(product_text)
        raw_terms = [
            term
            for term in re.findall(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]+", str(product_text or ""))
            if len(term) >= 3
        ]
        if not normalized_query or not raw_terms:
            return []

        today = date.today().isoformat()

        try:
            with SessionLocal() as session:
                # En uzun terimlerle filtrele (daha özgün sonuçlar)
                top_terms = sorted(set(raw_terms), key=len, reverse=True)[:6]
                clauses = [
                    EbtiKararModel.urun_tanimi.ilike(f"%{term}%")
                    for term in top_terms
                ]
                rows = session.query(EbtiKararModel).filter(
                    EbtiKararModel.durum.in_(["VALID", "VALID_EXPIRED", "UNKNOWN"]),
                    or_(*clauses),
                ).order_by(EbtiKararModel.karar_tarihi.desc()).limit(150).all()
        except Exception as exc:
            logger.warning("EBTI emsal araması tamamlanamadı: %s", exc)
            return []

        query_tokens = set(normalized_query.split())
        matches = []
        seen: set = set()

        for row in rows:
            key = (row.referans_no, row.kaynak_ulke)
            if key in seen:
                continue
            seen.add(key)

            # Geçerlilik kontrolü
            if row.gecerlilik_bitis and row.gecerlilik_bitis < today:
                if row.durum == "VALID":
                    continue  # Süresi dolmuş geçerli kararları atla

            desc_normalized = _normalize_product_text(str(row.urun_tanimi or ""))
            gerekce_normalized = _normalize_product_text(str(row.karar_gerekcesi or ""))
            combined_text = f"{desc_normalized} {gerekce_normalized}"
            desc_tokens = set(combined_text.split())

            overlap = len(query_tokens & desc_tokens)
            if overlap == 0:
                continue

            coverage = overlap / max(1, len(query_tokens))
            precision = overlap / max(1, len(desc_tokens))

            if normalized_query == desc_normalized:
                score = 1.0
            elif normalized_query in combined_text or desc_normalized in normalized_query:
                score = 0.95
            else:
                score = 0.65 * coverage + 0.35 * precision

            if score < 0.20:
                continue

            # EBTI skor ayarı: VALID durumu ve yakın tarih bonus alır
            if row.durum == "VALID":
                score = min(1.0, score * 1.05)

            cn8 = str(row.cn_kodu_8hane or "")
            ebti_url = str(row.kaynak_url or "https://ec.europa.eu/taxation_customs/dds2/ebti/")

            try:
                matches.append(PrecedentEBTI(
                    reference_no=str(row.referans_no or ""),
                    country=str(row.kaynak_ulke or "EU"),
                    cn_code=cn8,
                    issue_date=str(row.karar_tarihi or ""),
                    valid_until=str(row.gecerlilik_bitis) if row.gecerlilik_bitis else None,
                    product_description=str(row.urun_tanimi or "")[:800],
                    legal_justification=str(row.karar_gerekcesi or "")[:1000],
                    legal_justification_tr=None,  # ETL scripti Türkçe çeviri sağlar
                    language=str(row.dil or "en"),
                    similarity_score=round(min(1.0, score), 4),
                    source_url=ebti_url,
                    image_url=str(row.gorsel_url) if row.gorsel_url else None,
                ))
            except Exception as exc_row:
                logger.debug("EBTI PrecedentEBTI oluşturma hatası (ref=%s): %s", row.referans_no, exc_row)

        return sorted(matches, key=lambda item: item.similarity_score, reverse=True)[:top_k]



    @classmethod
    def exact_btb_candidate(cls, precedents: Sequence[PrecedentBTB]) -> Optional[GTIPCandidate]:
        """Accept an exact BTB match only when all exact records agree on one active leaf."""
        exact = [item for item in precedents if item.similarity_score >= 0.999]
        exact_codes = {_digits(item.gtip_code) for item in exact}
        if len(exact_codes) != 1:
            return None
        code = next(iter(exact_codes))
        try:
            with SessionLocal() as session:
                valid, record = validate_leaf_gtip(session, code)
        except Exception as exc:
            logger.warning("Exact BTB leaf validation failed: %s", exc)
            return None
        if not valid or not record:
            return None

        candidate = cls._candidate({
            "gtip_code": code,
            "description": str(record.get("description") or exact[0].product_description),
        })
        candidate.score = 0.99
        candidate.precedents = [item for item in exact if _digits(item.gtip_code) == code][:3]
        candidate.consulted_sources = ["BTB", "TGTC_2026", "GIR_1_6"]
        candidate.legal_sources.extend([
            LegalSource(
                source_type="BTB",
                reference_no=item.btb_no,
                title=f"Emsal BTB {item.btb_no}",
                publication_date=item.issue_date or None,
                excerpt=item.product_description,
                source_url=item.source_url,
                legal_role="INDIVIDUAL_PRECEDENT",
                authority_level=3,
                is_binding=False,
            )
            for item in candidate.precedents
        ])
        return candidate

    @staticmethod
    def _chapter_nodes() -> List[Dict[str, Any]]:
        headings = get_local_tgtc_headings()
        chapter_labels = load_tgtc_chapters()
        grouped: Dict[str, List[Tuple[str, str]]] = {}
        for code, value in headings.items():
            clean_code = _digits(code)
            grouped.setdefault(clean_code[:2], []).append((clean_code, str(value).strip()))

        nodes: List[Dict[str, Any]] = []
        for chapter in sorted(chapter_labels):
            # The catalog has no separate chapter-title rows. This compact
            # synopsis gives the model the real scope without product rules.
            scope = "; ".join(
                f"{code}: {value[:55]}"
                for code, value in grouped.get(chapter, [])
            )[:900]
            nodes.append({
                "gtip_code": chapter,
                "description": f"{chapter_labels[chapter]}. Pozisyon kapsamı: {scope}",
                "level": "CHAPTER",
            })
        return nodes

    @staticmethod
    def _heading_nodes(chapter: str) -> List[Dict[str, Any]]:
        clean_chapter = _digits(chapter).zfill(2)
        return [
            {
                "gtip_code": _digits(code),
                "description": description,
                "level": "HEADING",
            }
            for code, description in sorted(get_local_tgtc_headings().items())
            if _digits(code).startswith(clean_chapter) and len(_digits(code)) == 4
        ]

    @staticmethod
    def _leaf_nodes(parent_code: str) -> List[Dict[str, Any]]:
        """Load active official leaves under one already selected parent."""
        parent = _digits(parent_code)
        if len(parent) not in {4, 6}:
            return []

        records: Dict[str, Dict[str, Any]] = {}
        try:
            with SessionLocal() as session:
                rows = session.query(TgtcGtipModel).filter(
                    TgtcGtipModel.level == "GTIP",
                    TgtcGtipModel.is_active == True,
                    TgtcGtipModel.gtip_code.like(f"{parent}%"),
                ).order_by(TgtcGtipModel.gtip_code).all()
                for row in rows:
                    code = _digits(row.gtip_code)
                    if len(code) == 12 and code.startswith(parent):
                        records[code] = {
                            "gtip_code": code,
                            "description": str(row.description or ""),
                            "level": "GTIP",
                        }

                # Older/local installations may only have the normalized table.
                hierarchy_rows = session.query(TariffHierarchyModel).filter(
                    TariffHierarchyModel.is_leaf == True,
                    TariffHierarchyModel.gtip_code.like(f"{parent}%"),
                ).order_by(TariffHierarchyModel.gtip_code).all()
                for row in hierarchy_rows:
                    code = _digits(row.gtip_code)
                    if len(code) == 12 and code.startswith(parent):
                        records.setdefault(code, {
                            "gtip_code": code,
                            "description": str(row.description_tr or ""),
                            "level": "GTIP",
                        })
        except Exception as exc:
            logger.exception("Official leaf catalog could not be read: %s", exc)
            return []
        return list(records.values())

    @classmethod
    def _subheading_nodes(cls, heading: str) -> List[Dict[str, Any]]:
        """Load official six-digit rows; derive them from leaves only as fallback."""
        clean_heading = _digits(heading)
        records: Dict[str, Dict[str, Any]] = {}
        try:
            with SessionLocal() as session:
                rows = session.query(TgtcGtipModel).filter(
                    TgtcGtipModel.level == "SUBHEADING",
                    TgtcGtipModel.is_active == True,
                    TgtcGtipModel.gtip_code.like(f"{clean_heading}%"),
                ).order_by(TgtcGtipModel.gtip_code).all()
                for row in rows:
                    code = _digits(row.gtip_code)
                    if len(code) == 6:
                        records[code] = {
                            "gtip_code": code,
                            "description": str(row.description or ""),
                            "level": "SUBHEADING",
                        }
                hierarchy_rows = session.query(TariffHierarchyModel).filter(
                    TariffHierarchyModel.level == 6,
                    TariffHierarchyModel.gtip_code.like(f"{clean_heading}%"),
                ).order_by(TariffHierarchyModel.gtip_code).all()
                for row in hierarchy_rows:
                    code = _digits(row.gtip_code)
                    if len(code) == 6:
                        records.setdefault(code, {
                            "gtip_code": code,
                            "description": str(row.description_tr or ""),
                            "level": "SUBHEADING",
                        })
        except Exception as exc:
            logger.warning("Official subheading catalog could not be read: %s", exc)

        # Some source imports contain only a subset of the explicit six-digit
        # rows. The active twelve-digit leaves are authoritative for catalog
        # coverage, so always fill every missing six-digit parent from them.
        grouped: Dict[str, List[str]] = {}
        for leaf in cls._leaf_nodes(clean_heading):
            code = _digits(leaf["gtip_code"])[:6]
            description = _description(leaf)
            if description and description not in grouped.setdefault(code, []):
                grouped[code].append(description)

        for code, descriptions in grouped.items():
            records.setdefault(code, {
                "gtip_code": code,
                "description": f"{code} alt pozisyonu — " + "; ".join(descriptions[:12]),
                "level": "SUBHEADING",
            })

        contexts = _load_subheading_contexts()
        for code, node in records.items():
            context = contexts.get(code, {})
            if context.get("description"):
                node["branch_context"] = str(context["description"])
        return [records[code] for code in sorted(records)]

    @staticmethod
    def _question(
        session_id: str,
        level: str,
        nodes: Sequence[Dict[str, Any]],
        selection: CandidateSelection,
    ) -> Optional[DiscriminatorQuestion]:
        option_map = {f"N{index + 1}": node for index, node in enumerate(nodes)}
        model_alternatives = [
            option_map[option_id]
            for option_id in selection.alternative_candidate_ids
            if option_id in option_map
        ][:4]
        # For a small sibling set, the server—not the model—guarantees full
        # branch coverage in the user question. Larger sets stay model-bounded.
        alternatives = list(nodes) if 2 <= len(nodes) <= 4 else model_alternatives
        if len(alternatives) < 2:
            return None
        options = [
            f"{_digits(node.get('gtip_code'))} — {_description(node)[:420]}"
            for node in alternatives
        ]
        options.append("Bilinmiyor")
        target_branches = {
            str(index): _digits(node.get("gtip_code"))
            for index, node in enumerate(alternatives)
        }
        target_branches[str(len(alternatives))] = ""
        return DiscriminatorQuestion(
            session_id=session_id,
            parameter_name=f"tariff_{level.lower()}_criterion",
            question_text=(
                "Ürünün aşağıdaki teknik tanımlardan hangisine uyduğunu belirtiniz."
                if len(alternatives) > len(model_alternatives)
                else selection.question_text
                or "Ürün aşağıdaki resmî tarife tanımlarından hangisini karşılıyor?"
            ),
            options=options,
            target_branches=target_branches,
        )

    @staticmethod
    def _chapter_notes_for(level: str, nodes: List[Dict[str, Any]]) -> Optional[str]:
        """Bu seviyedeki seceneklerin faslina ait resmi notlari dondurur.

        GIR 1 siniflandirmanin pozisyon metinleri VE bolum/fasil notlarina gore
        yapilmasini emreder. Notlar daha once yalnizca karar verildikten sonra
        rapora ekleniyordu; model onlari hic gormeden seciyordu.

        CHAPTER seviyesinde 97 faslin notu prompta sigmaz ve o seviye zaten bir
        yonlendirme adimidir; fasil ici ayrim HEADING ve altinda yapilir.
        """
        if level == "CHAPTER" or not nodes:
            return None
        chapters = {_digits(node.get("gtip_code"))[:2] for node in nodes}
        chapters.discard("")
        if len(chapters) != 1:
            return None
        from api.db.tgtc_knowledge_base import load_tgtc_rules_and_notes
        note = load_tgtc_rules_and_notes().get("fasil_notlari", {}).get(next(iter(chapters)))
        note = str(note or "").strip()
        return note or None

    @classmethod
    def _select_node(
        cls,
        session_id: str,
        product_text: str,
        level: str,
        nodes: List[Dict[str, Any]],
        *,
        traversal: Optional[Dict[str, Any]] = None,
        precedents: Optional[Sequence[Any]] = None,
        rejected_codes: Optional[List[str]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[DiscriminatorQuestion], List[str], List[str]]:
        if not nodes:
            return None, None, [], []
        if len(nodes) == 1:
            return nodes[0], None, ["GIR_1", "GIR_6"], []

        # Ortak önek hem prompta hem soruya gürültü olarak giriyordu.
        nodes = _shorten_siblings(nodes)

        selection = llm_verifier.select_tariff_node(
            product_text,
            level,
            nodes,
            precedents=list(precedents or []) if settings.SELECTION_USE_PRECEDENTS else [],
            chapter_notes=(
                cls._chapter_notes_for(level, nodes)
                if settings.SELECTION_USE_CHAPTER_NOTES else None
            ),
            rejected_codes=list(rejected_codes or []) or None,
        )
        applied_gir_keys = list(getattr(selection, "applied_gir_keys", []) or [])
        cited_chapter_notes = list(getattr(selection, "cited_chapter_notes", []) or [])

        if selection.status == CandidateSelectionStatus.SELECT:
            match = re.fullmatch(r"N([1-9][0-9]*)", selection.selected_candidate_id or "")
            index = int(match.group(1)) - 1 if match else -1
            if 0 <= index < len(nodes):
                logger.info(
                    "Closed-set selection level=%s option=%s code=%s choices=%s",
                    level,
                    selection.selected_candidate_id,
                    _digits(nodes[index].get("gtip_code")),
                    len(nodes),
                )
                return nodes[index], None, applied_gir_keys, cited_chapter_notes
            logger.error("Selector returned an option id outside the server-owned set")
            return None, None, applied_gir_keys, cited_chapter_notes
        if selection.status == CandidateSelectionStatus.INSUFFICIENT_INFORMATION:
            logger.info(
                "Closed-set selection needs information level=%s alternatives=%s choices=%s",
                level,
                selection.alternative_candidate_ids,
                len(nodes),
            )
            return None, cls._question(session_id, level, nodes, selection), applied_gir_keys, cited_chapter_notes
        if level == "GTIP":
            residuals = [
                node
                for node in nodes
                if "diğer" in str(node.get("description") or "").casefold()
                or "diger" in str(node.get("description") or "").casefold()
            ]
            if len(residuals) == 1:
                logger.warning(
                    "Closed-set GTIP selection fell back to the single official residual leaf code=%s",
                    _digits(residuals[0].get("gtip_code")),
                )
                # Model hiçbir dalı eşleştiremedi; kalan tek "diğerleri" dalına
                # düşüldü. Bu zayıf bir seçimdir ve güven skorunu düşürmelidir.
                if traversal is not None:
                    traversal["used_residual_fallback"] = True
                return residuals[0], None, applied_gir_keys, cited_chapter_notes

        # Resmî kalıntı dalı da çözemediyse: NO_MATCH eskiden bir çıkmazdı.
        # Traversal ölüyor, karar MANUAL_REVIEW'a düşüyordu; ölçümde numunelerin
        # %35.8'i buradan kaybediliyor ve NO_MATCH retry'larının 62'si tek bir
        # seviyede (HEADING) yoğunlaşıyordu.
        #
        # Model "hiçbiri uymuyor" dediğinde aslında bildiğimiz tek şey seçim
        # yapamadığıdır. Resmî kardeş dalları müşavire sormak, sessizce pes
        # etmekten hem daha doğru hem daha kullanışlıdır. Seçenek kümesi
        # sorulabilecek kadar küçükse soruya çevrilir.
        if level != "CHAPTER" and 2 <= len(nodes) <= 4:
            fallback_question = cls._question(session_id, level, nodes, selection)
            if fallback_question:
                logger.info(
                    "Closed-set NO_MATCH recovered as a bounded question level=%s choices=%s",
                    level,
                    len(nodes),
                )
                return None, fallback_question, applied_gir_keys, cited_chapter_notes

        return None, None, applied_gir_keys, cited_chapter_notes

    @staticmethod
    def _candidate(
        node: Dict[str, Any],
        applied_gir_keys: Optional[List[str]] = None,
        cited_chapters: Optional[List[str]] = None,
    ) -> GTIPCandidate:
        code = _digits(node.get("gtip_code"))
        description = _description(node)
        from api.db.tgtc_knowledge_base import get_official_statute_records
        official_sources = get_official_statute_records(
            gtip_code=code,
            applied_gir_keys=applied_gir_keys,
            cited_chapters=cited_chapters,
        )
        return GTIPCandidate(
            gtip_code=code,
            description=description,
            chapter=code[:2],
            heading=code[:4],
            score=0.90,
            legal_sources=official_sources,
            consulted_sources=["TGTC_2026", "GIR_1_6"],
        )

    def search_candidates_hierarchical(
        self,
        session_id: str,
        features: ProductFeatures,
        allowed_chapters: Optional[List[str]] = None,
        applied_gir_rules: Optional[List[str]] = None,
        locked_chapter: Optional[str] = None,
        locked_heading: Optional[str] = None,
        locked_subheading: Optional[str] = None,
        locked_gtip: Optional[str] = None,
        query_vector: Optional[List[float]] = None,
        raw_text: str = "",
        precedents: Optional[Sequence[Any]] = None,
    ) -> HierarchicalSearchResult:
        """Traverse chapter → heading → subheading → leaf with model choices."""
        del applied_gir_rules  # Compatibility only; no product-routing rules remain.
        product_text = self._product_text(
            features, raw_text if settings.SELECTION_USE_RAW_TEXT else ""
        )
        traversal: Dict[str, Any] = {"query_vector": query_vector}

        applied_gir_keys: List[str] = list(traversal.get("applied_gir_keys") or [])
        cited_chapter_notes: List[str] = list(traversal.get("cited_chapter_notes") or [])

        def _merge_rules(g_keys: List[str], c_notes: List[str]):
            for k in g_keys:
                if k not in applied_gir_keys:
                    applied_gir_keys.append(k)
            for c in c_notes:
                if c not in cited_chapter_notes:
                    cited_chapter_notes.append(c)
            traversal["applied_gir_keys"] = applied_gir_keys
            traversal["cited_chapter_notes"] = cited_chapter_notes

        if not locked_chapter and allowed_chapters:
            locked_chapter = _digits(allowed_chapters[0]).zfill(2)

        # Fasıl seçimi tek yönlüydü: CHAPTER seviyesinde model SELECT etmek
        # zorunda (prompt orada INSUFFICIENT_INFORMATION'ı yasaklar), yanlış
        # seçerse doğru pozisyon o fasılda hiç bulunmaz ve sistem kurtaramazdı.
        # Pozisyon seçimi tamamen başarısız olursa fasıl, başarısız olan dışlanarak
        # bir kez yeniden seçilir.
        rejected_chapters: List[str] = []
        max_chapter_attempts = 2

        for attempt in range(max_chapter_attempts):
            if not locked_chapter:
                # Reddedilen fasıl listeden ÇIKARILMAZ: option_id konumsaldır,
                # çıkarmak tüm kimlikleri kaydırır. Dışlama modele bildirilir.
                node, question, g_keys, c_notes = self._select_node(
                    session_id, product_text, "CHAPTER", self._chapter_nodes(),
                    traversal=traversal, precedents=precedents,
                    rejected_codes=rejected_chapters or None,
                )
                _merge_rules(g_keys, c_notes)
                if question:
                    traversal.update({"pending_level": "CHAPTER", "branches": self._question_branches(question)})
                    return HierarchicalSearchResult(discriminator_question=question, traversal_state=traversal)
                if not node:
                    return HierarchicalSearchResult(traversal_state=traversal)
                locked_chapter = _digits(node["gtip_code"]).zfill(2)
            traversal.update({"locked_chapter": locked_chapter, "retained_chapters": [locked_chapter]})

            if locked_heading:
                break

            node, question, g_keys, c_notes = self._select_node(
                session_id, product_text, "HEADING", self._heading_nodes(locked_chapter),
                traversal=traversal, precedents=precedents,
            )
            _merge_rules(g_keys, c_notes)
            if question:
                traversal.update({"pending_level": "HEADING", "branches": self._question_branches(question)})
                return HierarchicalSearchResult(discriminator_question=question, traversal_state=traversal)
            if node:
                locked_heading = _digits(node["gtip_code"])
                break

            # Pozisyon bulunamadı: büyük olasılıkla fasıl yanlış seçildi.
            if attempt + 1 < max_chapter_attempts:
                logger.warning(
                    "No heading matched in chapter=%s; backtracking to chapter selection",
                    locked_chapter,
                )
                rejected_chapters.append(locked_chapter)
                traversal["rejected_chapters"] = list(rejected_chapters)
                traversal["used_chapter_backtrack"] = True
                locked_chapter = None
                continue
            return HierarchicalSearchResult(traversal_state=traversal)

        if not locked_heading:
            return HierarchicalSearchResult(traversal_state=traversal)
        if len(_digits(locked_heading)) != 4 or not _digits(locked_heading).startswith(locked_chapter):
            return HierarchicalSearchResult(traversal_state=traversal)
        traversal["locked_heading"] = locked_heading

        subheading_nodes = self._subheading_nodes(locked_heading)
        if not locked_subheading:
            node, question, g_keys, c_notes = self._select_node(
                session_id, product_text, "SUBHEADING", subheading_nodes,
                traversal=traversal, precedents=precedents,
            )
            _merge_rules(g_keys, c_notes)
            if question:
                traversal.update({"pending_level": "SUBHEADING", "branches": self._question_branches(question)})
                return HierarchicalSearchResult(discriminator_question=question, traversal_state=traversal)
            if not node:
                return HierarchicalSearchResult(traversal_state=traversal)
            locked_subheading = _digits(node["gtip_code"])
        if len(_digits(locked_subheading)) != 6 or not _digits(locked_subheading).startswith(_digits(locked_heading)):
            return HierarchicalSearchResult(traversal_state=traversal)
        traversal["locked_subheading"] = locked_subheading

        leaves = self._leaf_nodes(locked_subheading)
        selected_subheading = next(
            (
                node for node in subheading_nodes
                if _digits(node.get("gtip_code")) == _digits(locked_subheading)
            ),
            {},
        )
        # Yaprak açıklamaları kökten yaprağa tam yol taşıdığı için ebeveyn
        # bağlamını başa eklemek yolu ikiye katlıyordu. Bunun yerine kardeşlerin
        # paylaştığı ortak önek atılarak ayrım öne çıkarılır.
        parent_context = _description(selected_subheading)
        if parent_context and leaves and " > " not in _description(leaves[0]):
            # Eski biçimli (yol taşımayan) katalog: ebeveyn bağlamı hâlâ gerekli.
            leaves = [
                {**leaf, "branch_context": f"{parent_context} > {_description(leaf)}"}
                for leaf in leaves
            ]
        if not locked_gtip:
            node, question, g_keys, c_notes = self._select_node(
                session_id, product_text, "GTIP", leaves,
                traversal=traversal, precedents=precedents,
            )
            _merge_rules(g_keys, c_notes)
            if question:
                traversal.update({"pending_level": "GTIP", "branches": self._question_branches(question)})
                return HierarchicalSearchResult(discriminator_question=question, traversal_state=traversal)
            if not node:
                return HierarchicalSearchResult(traversal_state=traversal)
            locked_gtip = _digits(node["gtip_code"])
        locked_gtip = _digits(locked_gtip)
        selected_leaf = next(
            (node for node in leaves if _digits(node.get("gtip_code")) == locked_gtip),
            None,
        )
        if not selected_leaf or len(locked_gtip) != 12:
            return HierarchicalSearchResult(traversal_state=traversal)
        traversal["locked_gtip"] = locked_gtip
        return HierarchicalSearchResult(
            candidates=[self._candidate(selected_leaf, applied_gir_keys, cited_chapter_notes)],
            traversal_state=traversal,
        )

    @staticmethod
    def _question_branches(question: DiscriminatorQuestion) -> List[Dict[str, Any]]:
        return [
            {
                "gtip_code": question.target_branches[str(index)],
                "description": label,
            }
            for index, label in enumerate(question.options[:-1])
        ]


rag_engine = RAGEngine()
