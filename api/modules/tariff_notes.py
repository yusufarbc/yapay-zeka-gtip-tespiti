"""Bölüm ve fasıl notları: ayrıştırma, akıllı kısaltma, dışlama hükümleri.

Kaynak veride bölüm notları ayrı tutulmaz; her bölümün İLK faslının notunun
başında gömülüdür (ör. Bölüm XV notları Fasıl 72'nin metninde). Bu yüzden Fasıl
73 veya 76 sınıflandırılırken Bölüm XV notları modele hiç ulaşmıyordu; Fasıl
85 için Bölüm XVI notları da (84'ün metninde) öyle.

Uzun notlar prompta düz kesilerek (ilk 6000 karakter) veriliyordu: 84, 85, 72
gibi fasıllarda notun üçte ikisi, bazen dışlama hükümleriyle birlikte, düşüyordu.
Kısaltma artık madde bazındadır: önce dışlama hükümleri, sonra tanımlar, sonra
diğer maddeler sığdığı kadar; atlanan madde sayısı belirtilir.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Armonize Sistem bölüm yapısı (TGTC ile aynı). Fasıl 77 ayrılmıştır.
SECTION_RANGES: Dict[str, Tuple[int, int]] = {
    "I": (1, 5), "II": (6, 14), "III": (15, 15), "IV": (16, 24), "V": (25, 27),
    "VI": (28, 38), "VII": (39, 40), "VIII": (41, 43), "IX": (44, 46), "X": (47, 49),
    "XI": (50, 63), "XII": (64, 67), "XIII": (68, 70), "XIV": (71, 71), "XV": (72, 83),
    "XVI": (84, 85), "XVII": (86, 89), "XVIII": (90, 92), "XIX": (93, 93), "XX": (94, 96),
    "XXI": (97, 97),
}

_EXCLUSION = re.compile(
    r"dahil\s+de[ğg]ildir|kapsamaz|kapsam[ıi]\s+d[ıi][şs][ıi]|hari[çc]|girmez|dahil\s+edilmez|"
    r"s[ıi]n[ıi]fland[ıi]r[ıi]lmaz|yer\s+almaz",
    re.IGNORECASE,
)
_DEFINITION = re.compile(
    r"tabiri|deyimi|terimi|tan[ıi]mlanm[ıi][şs]t[ıi]r|anlam[ıi]na|kastedil|say[ıi]l[ıi]r|ifade\s+eder",
    re.IGNORECASE,
)
# Üst düzey not maddesi ("1. …", "2 - …") veya not başlığı.
_BLOCK_START = re.compile(r"^\s*(\d{1,2}\s*[\.\-–]\s|Notlar\b|Alt\s+Pozisyon\s+Notlar|Ek\s+Not)", re.IGNORECASE)


def section_of(chapter: str) -> Optional[str]:
    number = int(re.sub(r"\D", "", str(chapter)) or 0)
    for roman, (start, end) in SECTION_RANGES.items():
        if start <= number <= end:
            return roman
    return None


def cited_note_refs(entries: Any) -> Tuple[List[str], List[str]]:
    """Modelin atıf listesini (fasıllar, bölümler) olarak ayırır.

    Model atıfları serbest biçimde yazıyor ("73", "XV_1f", "FASIL 73 NOTLARI 1",
    "BÖLÜM XV NOTLARI 3"). Rakamları toplamak "XV_1f"i Fasıl 01'e, dolayısıyla
    Bölüm I'e (canlı hayvanlar) çeviriyordu ve tencere kararının kaynaklarında
    Bölüm I notları görünüyordu. Yalnız açıkça fasıl veya bölüm bildiren atıf
    kabul edilir; gerisi yok sayılır.
    """
    chapters: List[str] = []
    sections: List[str] = []
    for entry in entries or []:
        text = str(entry or "").strip()
        folded = text.casefold()
        chapter = None
        if re.fullmatch(r"\d{1,2}", text):
            chapter = text
        else:
            match = re.search(r"fas[iı]l\s*(\d{1,2})\b", folded)
            chapter = match.group(1) if match else None
        if chapter and 1 <= int(chapter) <= 97:
            code = chapter.zfill(2)
            if code not in chapters:
                chapters.append(code)
            continue
        match = re.search(r"b[öo]l[üu]m\s+([ivxl]+)\b", folded) or re.match(r"([ivxl]+)(?:[_\s.]|$)", folded)
        roman = match.group(1).upper() if match else None
        if roman in SECTION_RANGES and roman not in sections:
            sections.append(roman)
    return chapters, sections


def _first_chapter(roman: str) -> str:
    return f"{SECTION_RANGES[roman][0]:02d}"


def _raw_notes() -> Dict[str, str]:
    # load_tgtc_rules_and_notes kendisi önbelleklidir.
    from api.db.tgtc_knowledge_base import load_tgtc_rules_and_notes

    return dict(load_tgtc_rules_and_notes().get("fasil_notlari", {}) or {})


def _split(chapter: str) -> Tuple[str, str]:
    """Faslın ham notunu (bölüm bloğu, fasıl bloğu) olarak ayırır."""
    code = f"{int(chapter):02d}"
    text = str(_raw_notes().get(code) or "")
    match = re.search(rf"FASIL\s+0?{int(code)}\b", text)
    if match and re.match(r"\s*B[ÖO]L[ÜU]M\s+[IVXL]+", text):
        return text[: match.start()].strip(), text[match.start():].strip()
    return "", text.strip()


def chapter_notes(chapter: str) -> str:
    """Yalnız faslın kendi notu (bölüm bloğu ayrılmış)."""
    return _split(chapter)[1]


def section_notes(roman: str) -> Optional[str]:
    """Bölüm notu; bölümün yalnız başlığı varsa (not maddesi yoksa) None."""
    if roman not in SECTION_RANGES:
        return None
    block = _split(_first_chapter(roman))[0]
    return block if re.search(r"\n\s*\d{1,2}\s*[\.\-–]\s", "\n" + block) else None


def _blocks(text: str) -> List[str]:
    blocks: List[List[str]] = [[]]
    for line in text.splitlines():
        if _BLOCK_START.match(line) and blocks[-1]:
            blocks.append([])
        blocks[-1].append(line)
    return ["\n".join(b).strip() for b in blocks if "\n".join(b).strip()]


def condense(text: str, budget: int) -> str:
    """Notu madde bazında `budget` karaktere sığdırır.

    Öncelik: dışlama hükümleri > tanımlar > diğer maddeler. Seçilen maddeler
    özgün sırasıyla verilir; atlanan madde sayısı sonda belirtilir. Tek bir
    dışlama maddesi bütçeden uzunsa o madde kesilir (dışlama asla tümden düşmez).
    """
    text = (text or "").strip()
    if len(text) <= budget:
        return text
    blocks = _blocks(text)

    def priority(block: str) -> int:
        if _EXCLUSION.search(block):
            return 0
        if _DEFINITION.search(block):
            return 1
        return 2

    order = sorted(range(len(blocks)), key=lambda i: (priority(blocks[i]), i))
    chosen, used = set(), 0
    for index in order:
        size = len(blocks[index]) + 1
        if used + size <= budget:
            chosen.add(index)
            used += size
        elif priority(blocks[index]) == 0 and budget - used > 200:
            blocks[index] = blocks[index][: budget - used - 20] + " …"
            chosen.add(index)
            used = budget
    omitted = len(blocks) - len(chosen)
    result = "\n".join(blocks[i] for i in sorted(chosen))
    if omitted:
        result += f"\n[… sığmayan {omitted} not maddesi verilmedi]"
    return result


def exclusion_clauses(chapter: str, budget: int = 4000) -> str:
    """Faslın ve bölümünün yalnız dışlama hükümleri (fasıl dışlama kontrolü için)."""
    parts = []
    roman = section_of(chapter)
    section = section_notes(roman) if roman else None
    for label, text in ((f"BÖLÜM {roman} NOTLARI", section), (f"FASIL {int(chapter):02d} NOTLARI", chapter_notes(chapter))):
        clauses = [b for b in _blocks(text or "") if _EXCLUSION.search(b)]
        if clauses:
            parts.append(f"{label}:\n" + "\n".join(clauses))
    return condense("\n\n".join(parts), budget) if parts else ""


def notes_for_prompt(chapters: Sequence[str], budget: int) -> Optional[str]:
    """Seçeneklerin fasılları için bölüm + fasıl notları, bütçe paylaşılarak.

    Aynı bölümdeki fasıllar bölüm notunu bir kez paylaşır. Önce her parçaya eşit
    pay verilir; kısa parçalardan artan pay uzun parçalara dağıtılır.
    """
    items: List[Tuple[str, str]] = []
    seen_sections = set()
    for chapter in sorted({f"{int(c):02d}" for c in chapters if str(c).strip()}):
        roman = section_of(chapter)
        section = section_notes(roman) if roman else None
        if section and roman not in seen_sections:
            seen_sections.add(roman)
            items.append((f"BÖLÜM {roman} NOTLARI", section))
        own = chapter_notes(chapter)
        if own:
            items.append((f"FASIL {chapter} NOTLARI", own))
    if not items:
        return None

    share = budget // len(items)
    spare = sum(max(0, share - len(text)) for _, text in items)
    long_items = [i for i, (_, text) in enumerate(items) if len(text) > share]
    bonus = spare // len(long_items) if long_items else 0
    parts = []
    for index, (label, text) in enumerate(items):
        limit = share + (bonus if index in long_items else 0)
        parts.append(f"{label}:\n{condense(text, max(400, limit - len(label) - 2))}")
    return "\n\n".join(parts)
