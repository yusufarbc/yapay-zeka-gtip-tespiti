"""
TGTC kataloğu metin kalitesi teşhisi.

Ham Excel dosyaları repoda tutulmaz. Bu betiği çalıştırmak için Ticaret Bakanlığı'nın
yayımladığı 2026 TGTC fasıl dosyalarını (*.xls) 'data/tgtc_xls/' dizinine indirin.

Sınıflandırmanın tavanını model değil, modelin okuduğu metin belirler. Bu araç
kataloğun seçim yapılabilir olup olmadığını ölçer ve ham Excel kaynağıyla
karşılaştırarak ne kadar ayırt edici metnin çıkarım sırasında kaybolduğunu
raporlar.

Üç sorun ölçülür:

1. AYIRT EDİLEMEZ YAPRAK — aynı 6 haneli ebeveyn altında birbiriyle özdeş metne
   sahip 12 haneli yapraklar. Model de müşavir de bunlar arasından seçemez.
2. KESİK AÇIKLAMA — Excel'de satır sarması ile devam eden açıklamaların ikinci
   satırı atıldığı için cümle ortasında biten kayıtlar.
3. KAYIP ARA BAŞLIK — kod sütunu boş, dash ile başlayan grup başlıkları. Tarife
   hiyerarşisinde ayrımı bunlar taşır; kod taşımadıkları için çıkarımda düşerler.

Kullanım:
  python -m scripts.diagnose_catalog_quality
  python -m scripts.diagnose_catalog_quality --source-check    # Excel'i de tarar (yavaş)
"""

import argparse
import collections
import json
import os
import re
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

CATALOG = os.path.join(root_dir, "data", "tgtc_2026_full_database.json")
SOURCE_DIR = os.path.join(root_dir, "data", "tgtc_xls")


def _digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _discriminating(text) -> str:
    """Dash ön-eklerini atarak yalnız ayırt edici metni bırakır."""
    stripped = re.sub(r"^[\s\-]+", "", str(text or "")).strip().casefold()
    return re.sub(r"\s+", " ", stripped)


def analyse_catalog(path: str = CATALOG) -> dict:
    with open(path, encoding="utf-8") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list):
        rows = rows.get("items") or rows.get("data") or []

    by_parent = collections.defaultdict(list)
    truncated = 0
    described = 0
    for row in rows:
        code = _digits(row.get("gtip_code") or row.get("code"))
        desc = str(row.get("description") or row.get("description_tr") or "").strip()
        if len(desc) >= 15:
            described += 1
            # Excel'de sarılan açıklamanın ikinci satırı atıldığında kayıt
            # noktalama olmadan, cümle ortasında biter.
            if len(desc) > 55 and not desc.endswith((":", ".", ")")):
                truncated += 1
        if len(code) == 12:
            by_parent[code[:6]].append(_discriminating(desc))

    total_leaves = sum(len(v) for v in by_parent.values())
    ambiguous = 0
    affected_parents = 0
    worst = []
    for parent, descs in by_parent.items():
        counts = collections.Counter(descs)
        dupes = sum(n for n in counts.values() if n > 1)
        if dupes:
            affected_parents += 1
            ambiguous += dupes
            worst.append((dupes, len(descs), parent, counts.most_common(1)[0]))

    return {
        "total_rows": len(rows),
        "total_leaves": total_leaves,
        "parents": len(by_parent),
        "ambiguous_leaves": ambiguous,
        "affected_parents": affected_parents,
        "described": described,
        "truncated": truncated,
        "worst": sorted(worst, reverse=True)[:15],
    }


def analyse_source(source_dir: str = SOURCE_DIR) -> dict:
    """Ham Excel'de kaç ayırt edici satırın koda bağlı OLMADIĞINI sayar."""
    import glob

    import pandas as pd

    coded = group_headings = continuations = 0
    for path in sorted(glob.glob(os.path.join(source_dir, "*.xls"))):
        try:
            frame = pd.read_excel(path, header=None, dtype=str).fillna("")
        except Exception:
            continue
        for row in frame.astype(str).values.tolist():
            code = _digits(row[0] if row else "")
            desc = (row[1] if len(row) > 1 else "").strip()
            if not desc:
                continue
            if code:
                coded += 1
            elif desc.lstrip().startswith("-"):
                group_headings += 1     # ara grup başlığı: ayrım burada
            else:
                continuations += 1      # önceki satırın devamı (sarma)
    return {
        "coded": coded,
        "group_headings": group_headings,
        "continuations": continuations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="TGTC katalog metin kalitesi teşhisi")
    parser.add_argument("--source-check", action="store_true",
                        help="Ham Excel dosyalarını da tara (yavaş, pandas gerekir)")
    args = parser.parse_args()

    stats = analyse_catalog()

    def pct(part, whole):
        return f"%{part / max(1, whole) * 100:.1f}"

    print("=== KATALOG (yüklenmiş JSON) ===")
    print(f"toplam kayıt              : {stats['total_rows']}")
    print(f"12 haneli yaprak          : {stats['total_leaves']}")
    print(f"6 haneli ebeveyn          : {stats['parents']}")
    print()
    print("1. AYIRT EDİLEMEZ YAPRAK")
    print(f"   kardeşiyle özdeş metinli: {stats['ambiguous_leaves']} "
          f"({pct(stats['ambiguous_leaves'], stats['total_leaves'])})")
    print(f"   etkilenen alt pozisyon  : {stats['affected_parents']} "
          f"({pct(stats['affected_parents'], stats['parents'])})")
    print()
    print("2. KESİK AÇIKLAMA")
    print(f"   cümle ortasında biten   : {stats['truncated']} "
          f"({pct(stats['truncated'], stats['described'])})")
    print()
    print("en kötü alt pozisyonlar (özdeş/toplam yaprak):")
    for dupes, total, parent, (label, count) in stats["worst"]:
        print(f"   {parent}  {dupes:>3}/{total:<3}  en sık: '{label[:44]}' x{count}")

    if args.source_check:
        src = analyse_source()
        lost = src["group_headings"] + src["continuations"]
        total = src["coded"] + lost
        print()
        print("=== HAM KAYNAK (Excel) ===")
        print(f"kodlu satır (içe aktarılan) : {src['coded']}")
        print(f"ara grup başlığı (kodsuz)   : {src['group_headings']}")
        print(f"devam satırı (sarma)        : {src['continuations']}")
        print(f"KAYIP ayırt edici satır     : {lost} ({pct(lost, total)})")
        print()
        print("Ara grup başlıkları kod sütunu boş olduğu için çıkarımda düşmüştür;")
        print("tarife hiyerarşisinde ayrımı taşıyan metin bunlardadır.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
