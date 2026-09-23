"""
Yeniden çıkarılan TGTC açıklamalarını Cloud SQL'e uygular.

KAPSAM — bilinçli olarak dar
---------------------------
Bu betik YALNIZCA mevcut satırların `description` sütununu günceller.

  - INSERT YAPMAZ. Yeni kod eklemek tarife kapsamını değiştirmek demektir;
    bu ayrı ve kendi onayı olan bir iştir.
  - DELETE YAPMAZ, `is_active` alanına DOKUNMAZ. Yürürlük kapısı
    (`validate_leaf_gtip`) bu alanlara dayanır; bir kodu yanlışlıkla
    pasifleştirmek o kodla yapılan her sınıflandırmayı reddeder.
  - Kod kümesini değiştirmez; yalnız aynı kodun metnini düzeltir.

Bu daraltma kasıtlıdır: yeniden çıkarım kod kümesini birebir koruduğu için
(15718 -> 15718) güncelleme metin düzeltmesinden ibarettir ve geri alınabilir.

Kullanım:
  python -m scripts.apply_catalog_descriptions                 # dry-run
  python -m scripts.apply_catalog_descriptions --apply
  python -m scripts.apply_catalog_descriptions --apply --limit-chapter 84
"""

import argparse
import logging
import os
import sys
from typing import Dict

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ApplyCatalogDescriptions")


DESCRIPTIONS_FILE = os.path.join(root_dir, "api", "data", "tgtc_descriptions.json")


def build_new_descriptions(limit_chapter: str = "", from_excel: bool = False) -> Dict[str, str]:
    """Açıklamaları üretilmiş eşleme dosyasından (varsayılan) veya ham Excel'den okur.

    Varsayılan dosyadır: ham Excel container imajında bulunmaz (.dockerignore),
    bu yüzden Cloud Run Job yalnız dosyayı okuyabilir. Excel yolu yerel
    geliştirme ve yeniden üretim içindir.
    """
    if from_excel:
        from scripts.rebuild_tgtc_catalog import rebuild
        rows = {r["gtip_code"]: r["description"] for r in rebuild()}
    else:
        import json

        if not os.path.exists(DESCRIPTIONS_FILE):
            raise RuntimeError(
                f"Açıklama dosyası yok: {DESCRIPTIONS_FILE}. "
                "Önce: python -m scripts.rebuild_tgtc_catalog --apply"
            )
        with open(DESCRIPTIONS_FILE, encoding="utf-8") as handle:
            rows = json.load(handle).get("descriptions") or {}

    if limit_chapter:
        return {c: d for c, d in rows.items() if c.startswith(limit_chapter)}
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="TGTC açıklamalarını Cloud SQL'de güncelle")
    parser.add_argument("--apply", action="store_true", help="Gerçekten yaz (varsayılan: dry-run)")
    parser.add_argument("--limit-chapter", type=str, default="",
                        help="Yalnız bu fasılla sınırla (örn. 84) — kademeli açılım için")
    parser.add_argument("--max-unknown-pct", type=float, default=2.0,
                        help="Veritabanında bulunamayan kod oranı eşiği (%%)")
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--from-excel", action="store_true",
                        help="Ham Excel'den yeniden üret (yerel; container'da Excel yoktur)")
    args = parser.parse_args()

    from api.db.database import SessionLocal, TgtcGtipModel

    logger.info("Açıklamalar yükleniyor (%s)...", "ham Excel" if args.from_excel else DESCRIPTIONS_FILE)
    new_desc = build_new_descriptions(args.limit_chapter, args.from_excel)
    logger.info("Üretilen kayıt: %d", len(new_desc))

    changed = unchanged = unknown = 0
    pending = []
    samples = []

    with SessionLocal() as session:
        query = session.query(TgtcGtipModel.gtip_code, TgtcGtipModel.description)
        if args.limit_chapter:
            query = query.filter(TgtcGtipModel.gtip_code.like(f"{args.limit_chapter}%"))
        existing = {code: desc for code, desc in query.all()}
        logger.info("Veritabanındaki kayıt: %d", len(existing))

        for code, desc in new_desc.items():
            current = existing.get(code)
            if current is None:
                unknown += 1
                continue
            if (current or "").strip() == desc.strip():
                unchanged += 1
                continue
            changed += 1
            pending.append((code, desc))
            if len(samples) < 5:
                samples.append((code, current, desc))

        unknown_pct = unknown / max(1, len(new_desc)) * 100

        print()
        print("=== PLANLANAN GÜNCELLEME ===")
        print(f"metni değişecek : {changed}")
        print(f"zaten aynı      : {unchanged}")
        print(f"DB'de yok       : {unknown} (%{unknown_pct:.1f})")
        print()
        for code, before, after in samples:
            print(f"{code}")
            print(f"   ÖNCE : {(before or '')[:100]}")
            print(f"   SONRA: {after[:100]}")

        if unknown_pct > args.max_unknown_pct:
            print()
            logger.error(
                "DURDURULDU: üretilen kodların %%%.1f'i veritabanında yok (eşik %%%.1f). "
                "Bu, kaynak ile veritabanının aynı tarife yılına ait olmadığını gösterebilir.",
                unknown_pct, args.max_unknown_pct,
            )
            return 1

        if not args.apply:
            print()
            print("DRY-RUN: veritabanına yazılmadı. Yazmak için --apply verin.")
            return 0

        logger.info("%d kayıt güncelleniyor (yalnız description sütunu)...", len(pending))
        written = 0
        for start in range(0, len(pending), args.batch):
            chunk = pending[start:start + args.batch]
            for code, desc in chunk:
                session.query(TgtcGtipModel).filter(
                    TgtcGtipModel.gtip_code == code
                ).update({TgtcGtipModel.description: desc}, synchronize_session=False)
            session.commit()
            written += len(chunk)
            logger.info("  %d/%d", written, len(pending))

    logger.info("Tamamlandı: %d açıklama güncellendi. Kod kümesi ve is_active değişmedi.", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
