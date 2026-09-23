"""
2026 TGTC kataloğunu ham Excel'den hiyerarşisi korunarak yeniden çıkarır.

SORUN
-----
Mevcut katalog, ham cetveldeki iki satır türünü atmış:

  1. ARA GRUP BAŞLIKLARI — kod sütunu boş, dash ile başlayan satırlar. Tarife
     ağacındaki ayrımı bunlar taşır.
  2. DEVAM SATIRLARI — Excel'de sarılan açıklamanın ikinci satırı; kod sütunu
     boş ve dash ile BAŞLAMAZ.

Sonuç: 15718 yaprağın 3645'i (%23.2) kardeşiyle özdeş metne sahip, 3815 açıklama
cümle ortasında kesik. `841370` altında 22 yaprağın tamamı ya "Diğerleri" ya
"Sivil hava taşıtlarında kullanılmaya mahsus olanlar" yazıyor — ne model ne
müşavir seçim yapabilir.

ÇÖZÜM
-----
Satırlar sırayla okunur; dash sayısı hiyerarşi derinliğini verir. Her kodlu satır
için kendinden yukarıdaki ataların metni birleştirilerek tam yol kurulur:

  841370219000
    şu an : "- Diğer santrifüj pompalar: > - - - - Diğerleri"
    sonra : "Diğer santrifüj pompalar > Dalgıç pompaları > Tek kademeli olanlar
             > Diğerleri"

GÜVENLİK
-------
Bu betik yetkili kataloğu yeniden yazar; `validate_leaf_gtip` buna dayanır ve
hatalı bir çıktı her kararın reddedilmesine yol açar. Bu yüzden:

  - Varsayılan DRY-RUN'dır; --apply verilmeden hiçbir dosya yazılmaz.
  - Kod kümesi mevcut katalogla karşılaştırılır. Kaybolan kod oranı eşiği aşarsa
    (--max-missing-pct, varsayılan %1) işlem durur.
  - Çıktı yalnız JSON'a yazılır; veritabanına dokunulmaz. Yükleme ayrı ve kendi
    kapıları olan bir adımdır (seed_tgtc_2026 / populate_tgtc_cloudsql).

Kullanım:
  python -m scripts.rebuild_tgtc_catalog                      # dry-run + rapor
  python -m scripts.rebuild_tgtc_catalog --sample 8413.70     # tek dalı incele
  python -m scripts.rebuild_tgtc_catalog --apply --out <yol>  # yaz
"""

import argparse
import collections
import glob
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RebuildTGTC")

SOURCE_DIR = os.path.join(root_dir, "2026 TGTC", "2026 TGTC")
CURRENT_CATALOG = os.path.join(root_dir, "2026 TGTC", "tgtc_2026_full_database.json")

# Bir açıklamanın kaç "- " öneki taşıdığı hiyerarşi derinliğini verir.
_DASH_PREFIX = re.compile(r"^((?:\s*-)+)\s*")


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def dash_depth(text: str) -> int:
    """Açıklamanın başındaki dash sayısı = tarife ağacındaki derinlik."""
    match = _DASH_PREFIX.match(str(text or ""))
    if not match:
        return 0
    return match.group(1).count("-")


def strip_dashes(text: str) -> str:
    return _DASH_PREFIX.sub("", str(text or "")).strip()


def parse_chapter(path: str) -> List[Dict[str, Any]]:
    """Bir fasıl dosyasını hiyerarşi korunarak ayrıştırır."""
    import pandas as pd

    frame = pd.read_excel(path, header=None, dtype=str).fillna("")
    raw_rows = frame.astype(str).values.tolist()

    entries: List[Dict[str, Any]] = []
    # derinlik -> o derinlikteki en son başlık metni
    ancestors: Dict[int, str] = {}
    last_entry: Optional[Dict[str, Any]] = None
    last_depth = 0

    for raw in raw_rows:
        code_cell = (raw[0] if len(raw) > 0 else "").strip()
        desc_cell = (raw[1] if len(raw) > 1 else "").strip()
        unit_cell = (raw[2] if len(raw) > 2 else "").strip()

        if not desc_cell:
            continue

        code = _digits(code_cell)
        depth = dash_depth(desc_cell)
        own_text = strip_dashes(desc_cell)

        # Devam satırı: kod yok VE dash yok => önceki açıklamanın sarma devamı.
        # Bunlar atıldığı için kodlu kayıtlar bile cümle ortasında kesiliyordu.
        if not code and depth == 0:
            if last_entry is not None:
                last_entry["own_text"] = f"{last_entry['own_text']} {own_text}".strip()
                if last_depth:
                    ancestors[last_depth] = last_entry["own_text"]
            continue

        # Bu derinlikteki başlığı güncelle, daha derin atalar geçersizleşir.
        ancestors[depth] = own_text
        for deeper in [d for d in ancestors if d > depth]:
            ancestors.pop(deeper, None)

        entry = {
            "code": code,
            "depth": depth,
            "own_text": own_text,
            "unit": unit_cell,
            # Ata metinleri kopyalanır: sonraki satırlar ancestors'ı değiştirir.
            "ancestor_depths": sorted(d for d in ancestors if d < depth),
            "ancestors_snapshot": {d: ancestors[d] for d in ancestors if d < depth},
        }
        entries.append(entry)
        last_entry = entry
        last_depth = depth

    return entries


def build_full_path(entry: Dict[str, Any], max_chars: int = 900) -> str:
    """Ata başlıklarını ve kendi metnini birleştirerek okunur tam yol üretir."""
    parts = [entry["ancestors_snapshot"][d].rstrip(":").strip()
             for d in entry["ancestor_depths"]]
    parts.append(entry["own_text"].rstrip(":").strip())
    # Ardışık tekrarları ele ("Diğerleri > Diğerleri" gibi) — bilgi taşımazlar.
    deduped: List[str] = []
    for part in parts:
        if part and (not deduped or deduped[-1].casefold() != part.casefold()):
            deduped.append(part)

    # Kırpma BAŞTAN yapılır. Ayırt edici metin daima en sondadır: balık türleri
    # gibi uzun dallarda sondan kesmek, kardeşleri yeniden özdeş hale getiriyordu.
    # Gerekirse en genel atalar düşürülür, en özel seviyeler korunur.
    while len(" > ".join(deduped)) > max_chars and len(deduped) > 1:
        deduped.pop(0)
    joined = " > ".join(deduped)
    if len(joined) > max_chars:
        # Tek seviye bile sığmıyorsa sondan tut; ayrım orada.
        joined = "…" + joined[-(max_chars - 1):]
    return joined


def rebuild(source_dir: str = SOURCE_DIR) -> List[Dict[str, Any]]:
    files = sorted(glob.glob(os.path.join(source_dir, "*.xls")))
    if not files:
        raise RuntimeError(f"Kaynak Excel bulunamadı: {source_dir}")

    catalog: List[Dict[str, Any]] = []
    for path in files:
        try:
            entries = parse_chapter(path)
        except Exception as exc:
            logger.warning("Fasıl okunamadı (%s): %s", os.path.basename(path), exc)
            continue
        for entry in entries:
            if not entry["code"]:
                continue   # ara grup başlığı: kendisi kayıt değil, bağlam taşır
            catalog.append({
                "gtip_code": entry["code"],
                "description": build_full_path(entry),
                "own_text": entry["own_text"],
                "unit": entry["unit"],
                "depth": entry["depth"],
            })
    return catalog


def load_current(path: str = CURRENT_CATALOG) -> Dict[str, str]:
    with open(path, encoding="utf-8") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list):
        rows = rows.get("items") or rows.get("data") or []
    return {
        _digits(r.get("gtip_code")): str(r.get("description") or "")
        for r in rows if _digits(r.get("gtip_code"))
    }


def _discriminating(text: str) -> str:
    stripped = re.sub(r"^[\s\-]+", "", str(text or "")).strip().casefold()
    return re.sub(r"\s+", " ", stripped)


def ambiguity_stats(codes_to_desc: Dict[str, str]) -> Dict[str, int]:
    by_parent = collections.defaultdict(list)
    for code, desc in codes_to_desc.items():
        if len(code) == 12:
            by_parent[code[:6]].append(_discriminating(desc))
    total = sum(len(v) for v in by_parent.values())
    ambiguous = 0
    for descs in by_parent.values():
        counts = collections.Counter(descs)
        ambiguous += sum(n for n in counts.values() if n > 1)
    return {"leaves": total, "ambiguous": ambiguous, "parents": len(by_parent)}


def main() -> int:
    parser = argparse.ArgumentParser(description="TGTC kataloğunu hiyerarşiyle yeniden çıkar")
    parser.add_argument("--apply", action="store_true", help="Çıktıyı dosyaya yaz (varsayılan: dry-run)")
    parser.add_argument("--out", type=str, default=None, help="Çıktı JSON yolu")
    parser.add_argument("--sample", type=str, default=None, help="Tek bir dalı incele (örn. 8413.70)")
    parser.add_argument("--max-missing-pct", type=float, default=1.0,
                        help="Mevcut katalogdan kaybolabilecek azami kod oranı (%%)")
    args = parser.parse_args()

    logger.info("Ham Excel ayrıştırılıyor: %s", SOURCE_DIR)
    rebuilt = rebuild()
    new_map = {r["gtip_code"]: r["description"] for r in rebuilt}
    current = load_current()

    if args.sample:
        prefix = _digits(args.sample)
        print(f"\n=== {args.sample} dalı ===")
        for code in sorted(c for c in new_map if c.startswith(prefix) and len(c) == 12):
            print(f"\n{code}")
            print(f"  ŞU AN : {current.get(code, '(yok)')[:110]}")
            print(f"  SONRA : {new_map[code][:110]}")
        return 0

    old_codes = {c for c in current if len(c) == 12}
    new_codes = {c for c in new_map if len(c) == 12}
    missing = old_codes - new_codes
    added = new_codes - old_codes
    missing_pct = len(missing) / max(1, len(old_codes)) * 100

    before = ambiguity_stats({c: d for c, d in current.items() if len(c) == 12})
    after = ambiguity_stats({c: d for c, d in new_map.items() if len(c) == 12})

    def pct(part, whole):
        return f"%{part / max(1, whole) * 100:.1f}"

    print()
    print("=== KOD KÜMESİ ===")
    print(f"mevcut 12 haneli : {len(old_codes)}")
    print(f"yeni 12 haneli   : {len(new_codes)}")
    print(f"kaybolan         : {len(missing)} ({pct(len(missing), len(old_codes))})")
    print(f"eklenen          : {len(added)}")
    print()
    print("=== AYIRT EDİLEBİLİRLİK ===")
    print(f"özdeş metinli yaprak ÖNCE : {before['ambiguous']} ({pct(before['ambiguous'], before['leaves'])})")
    print(f"özdeş metinli yaprak SONRA: {after['ambiguous']} ({pct(after['ambiguous'], after['leaves'])})")
    improvement = before["ambiguous"] - after["ambiguous"]
    print(f"ayırt edilebilir hale gelen: {improvement}")

    if missing_pct > args.max_missing_pct:
        print()
        logger.error(
            "DURDURULDU: kaybolan kod oranı %.2f%% > eşik %.2f%%. "
            "Yetkili katalogda kod kaybı her kararın reddedilmesine yol açar.",
            missing_pct, args.max_missing_pct,
        )
        for code in sorted(missing)[:10]:
            logger.error("  kayıp: %s -> %s", code, current.get(code, "")[:60])
        return 1

    if not args.apply:
        print()
        print("DRY-RUN: hiçbir dosya yazılmadı. Yazmak için --apply verin.")
        return 0

    # Ana katalog JSON'u DEĞİŞTİRİLMEZ: tax_rate, chapter, heading gibi alanları
    # taşıyor ve populate_tgtc_cloudsql bunları okuyor. Yalnız kod -> açıklama
    # eşlemesi yazılır; uygulama adımı da yalnız description sütununu günceller.
    out_path = args.out or os.path.join(root_dir, "api", "data", "tgtc_descriptions.json")
    payload = {
        "tariff_year": "2026",
        "generated_from": "2026 TGTC ham Excel (ara grup başlıkları ve satır sarmaları korunarak)",
        "descriptions": {r["gtip_code"]: r["description"] for r in rebuilt},
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    size_mb = os.path.getsize(out_path) / 1024 / 1024
    logger.info("Yazıldı: %s (%d açıklama, %.1f MB)", out_path, len(payload["descriptions"]), size_mb)
    logger.info("Veritabanına uygulama AYRI bir adımdır: scripts.apply_catalog_descriptions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
