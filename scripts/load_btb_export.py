"""
Dışa aktarılmış BTB kararlarını (data/btb_kararlari_export_*.json) veritabanına yükler.

Canlı sistemde BTB kararları yalnız Cloud SQL'de duruyordu. GCP kapatılmadan önce
canlı API'den 2.355 karar dışa aktarıldı; bu betik onları yerel veritabanına
(DATABASE_URL yoksa SQLite) yükler ki emsal araması yerelde de çalışsın.

Kullanım:
    python -m scripts.load_btb_export [data/btb_kararlari_export_2026-09-29.json]
"""

import json
import logging
import os
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from api.db.database import GumrukEmsalKararModel, SessionLocal, init_orm_tables  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LoadBTBExport")

DEFAULT_PATH = os.path.join(root_dir, "data", "btb_kararlari_export_2026-09-29.json")


def main(path: str = DEFAULT_PATH) -> int:
    with open(path, encoding="utf-8") as handle:
        records = json.load(handle)
    init_orm_tables()
    with SessionLocal() as session:
        existing = {
            ref for (ref,) in session.query(GumrukEmsalKararModel.referans_no)
            .filter(GumrukEmsalKararModel.karar_tipi == "BTB").all()
        }
        added = 0
        for item in records:
            ref = str(item.get("btb_no") or "").strip()
            description = str(item.get("product_description") or "").strip()
            gtip = str(item.get("gtip_code") or "").strip()
            if not ref or not description or not gtip or ref in existing:
                continue
            session.add(GumrukEmsalKararModel(
                karar_tipi="BTB",
                referans_no=ref,
                yayin_tarihi=item.get("issue_date"),
                gtip_kodu=gtip,
                chapter_code=item.get("chapter") or gtip[:2],
                esya_tanimi=description,
                hukuki_gerekce=item.get("legal_justification"),
                kaynak_url=item.get("source_url"),
            ))
            existing.add(ref)
            added += 1
        session.commit()
    logger.info("%d BTB kararı yüklendi (%d kayıt okundu).", added, len(records))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
