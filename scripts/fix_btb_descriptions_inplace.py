"""
Cloud SQL In-Place esya_tanimi Duzeltici
=========================================
- SADECE gumruk_emsal_kararlar ve gumruk_siniflandirma_kararlari tablolarini duzeltir
- tgtc_gtip, tgtc_rules, tgtc_notes, official_btbs tablolarina KESINLIKLE DOKUNMAZ
- Jenerik Teblig cumleleri (Bu Tebligin amaci, MADDE 1, Haksiz Rekabet...) olan
  esya_tanimi alanlari hukuki_gerekce metni uzerinden akilli regex ile duzeltilir
- Sadece UPDATE -- hicbir kayit silinmez

Kullanim:
  $env:DATABASE_URL = '<Cloud SQL Proxy uzerinden baglanti dizesi>'
  python scripts/fix_btb_descriptions_inplace.py            # dry-run (yazar olmadan gosterir)
  python scripts/fix_btb_descriptions_inplace.py --apply    # gercekten yazar
"""

import re
import sys
import logging
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BTBDescriptionFixer")

if not os.getenv("DATABASE_URL"):
    raise SystemExit(
        "Guvenlik nedeniyle DATABASE_URL acikca verilmelidir. Parola kaynak koda yazilmamalidir."
    )

from api.db.database import engine

# Jenerik / bozuk aciklama kaliplari
JENERIK_KALIPLAR = [
    r"^Bu Tebli[gG\u011f\u011e]in amac",
    r"^MADDE\s*[-\u2013]?\s*\(?\s*1\s*\)?",
    r"^Madde\s+\d+",
    r"^Haks[i\u0131]z Rekabetin",
    r"^[I\u0130i]thalatta Haks[i\u0131]z Rekabet",
    r"G[u\u00fc]mr[u\u00fc]k Genel Tebli[g\u011f]i",
    r"Resm[i\u0131] Gazete S[i\u0131]n[i\u0131]fland[i\u0131]rma",
    r"a\) Hizmet bedeli",
]

_BAD_DESC = [
    r"^Bu Tebli[g\u011f]in amac",
    r"^MADDE",
    r"^Madde\s+\d",
    r"Haks[i\u0131]z Rekabetin",
    r"G[u\u00fc]mr[u\u00fc]k Genel Tebli",
    r"Resm[i\u0131] Gazete",
    # GTİP istatistik/pozisyon referansi olan cumleleri REDDET
    r"g[u\u00fc]mr[u\u00fc]k tarife istatistik pozisyon",
    r"GT[I\u0130]P numaral[i\u0131] sat[i\u0131]r",
    r"GT[I\u0130]P.{1,10}numaral[i\u0131]",
    r"y[u\u00fc]r[u\u00fc]rl[u\u00fc]kten kald[i\u0131]r[i\u0131]l",
    r"^\d{2,4}[\.,]\d",  # Rakamla baslayan cумлелер
]


def is_jenerik(text_val):
    if not text_val:
        return True
    t = text_val.strip()
    return any(re.search(p, t, re.IGNORECASE) for p in JENERIK_KALIPLAR)


def bad(s):
    return any(re.search(p, s.strip(), re.IGNORECASE) for p in _BAD_DESC)


def extract_product_name(hukuki_gerekce, gtip=""):
    """
    hukuki_gerekce (orijinal Resmi Gazete metni) uzerinden
    gercek urun/esya adini cikarir. Cok katmanli hiyerarsik regex.
    """
    text_val = (hukuki_gerekce or "").strip()

    # 1. Tirnak ici urun adi -- EN ONCELIKLI (Ornek: "kakao yagi", "sodyum formiat")
    quotes = re.findall(r'"([^"]{4,150})"', text_val)
    for q in quotes:
        q = q.strip()
        if is_meaningful(q) and not any(k in q.lower() for k in [
            "resmi gazete", "tebli", "madde", "karar", "ek-", "sayili", "gumruk",
            "tarife istatistik", "pozisyon"
        ]):
            return q[:200]

    # 2. "Esya Tanimi:" etiketi
    m = re.search(
        r"e[s\u015f]ya\s+tan[i\u0131]m[i\u0131]\s*[:\-]\s*(.+?)(?:\n|hukuki|gerek[c\u00e7]e|$)",
        text_val, re.IGNORECASE
    )
    if m:
        c = m.group(1).strip().rstrip(".,;")
        if is_meaningful(c):
            return c[:200]

    # 3. "Konu:" / "Urun:" etiketi
    m = re.search(r"(?:konu|[u\u00fc]r[u\u00fc]n)\s*:\s*(.+?)(?:\n|$)", text_val, re.IGNORECASE)
    if m:
        c = m.group(1).strip().rstrip(".,;")
        if is_meaningful(c) and len(c) < 200:
            return c[:200]

    # 4. "yer alan ... ithalati/ihracati" kalibi
    m = re.search(
        r"yer alan\s+(.+?)(?:\s+ithalat[i\u0131]|\s+ihracat[i\u0131]"
        r"|\s+[u\u00fc]r[u\u00fc]nleri|\s+e[s\u015f]yalar|\s+kapsam[i\u0131]nda|\s+tabidir)",
        text_val, re.IGNORECASE
    )
    if m:
        c = m.group(1).strip().rstrip(".,;")
        if is_meaningful(c) and len(c) < 150:
            return c[:150]

    # 5. Mensel/urun kalibi (Ornek: "Cin menseli dokuma kumas")
    m = re.search(
        r"([A-Z\u00c7\u011e\u0130\u00d6\u015e\u00dca-z\u00e7\u011f\u0131\u00f6\u015f\u00fc][^\n]{5,80}"
        r"(?:kuma[s\u015f]|levha|boru|cihaz|[s\u015f]arap|bira|[c\u00e7]elik|menteye|otomobil"
        r"|i[l\u0131]a[c\u00e7]|kimya|plastik|tekstil|konserv|deri|profil|aksamlar))",
        text_val, re.IGNORECASE
    )
    if m:
        c = m.group(1).strip().rstrip(".,;")
        if is_meaningful(c) and len(c) < 200:
            return c[:200]

    return ""



def fix_table(conn, table, id_col, gtip_col, desc_col, gerekce_col, dry_run=True):
    """Belirtilen tabloda jenerik esya_tanimi kayitlarini in-place duzeltir."""
    logger.info(f"\n[{table}] Jenerik kayitlar taranıyor...")

    rows = conn.execute(text(f"""
        SELECT {id_col}, {gtip_col}, {desc_col}, {gerekce_col}
        FROM {table}
        WHERE {desc_col} ILIKE '%Bu Tebli%'
           OR {desc_col} ILIKE '%Haks%'
           OR {desc_col} ILIKE '%MADDE%'
           OR {desc_col} ILIKE '%amac%'
           OR {desc_col} ILIKE '%yayimlanan%'
           OR {desc_col} ILIKE '%a) Hizmet%'
           OR {desc_col} ILIKE '%Siniflandirma Karar%'
    """)).fetchall()

    logger.info(f"[{table}] {len(rows)} jenerik kayit bulundu.")

    fixed = 0
    fallbacks = 0

    for row in rows:
        row_id, gtip, old_desc, gerekce = row
        new_desc = extract_product_name(gerekce or "", gtip or "")

        if new_desc and new_desc.strip() and new_desc.strip() != (old_desc or "").strip():
            if dry_run:
                logger.info(f"  [DRY-RUN] ID={row_id} | GTIP={gtip}")
                logger.info(f"    ESKI : {(old_desc or '')[:80]}")
                logger.info(f"    YENI : {new_desc[:80]}")
            else:
                conn.execute(text(f"""
                    UPDATE {table}
                    SET {desc_col} = :new_desc
                    WHERE {id_col} = :row_id
                """), {"new_desc": new_desc, "row_id": row_id})
                logger.info(f"  GUNCELLENDI ID={row_id} | {new_desc[:70]}")
            fixed += 1
        else:
            fallback_desc = f"Gumruk Siniflandirma Karari - GTIP {gtip}"
            if not dry_run:
                conn.execute(text(f"""
                    UPDATE {table}
                    SET {desc_col} = :new_desc
                    WHERE {id_col} = :row_id
                """), {"new_desc": fallback_desc, "row_id": row_id})
            logger.info(f"  FALLBACK ID={row_id} | urun adi cikarilamadi, GTIP ref yazildi")
            fallbacks += 1

    logger.info(f"[{table}] TAMAMLANDI -- {fixed} duzeltildi, {fallbacks} fallback yazildi")
    return fixed, fallbacks


def run_patch(dry_run=True):
    logger.info("=" * 60)
    logger.info(f"BTB/Siniflandirma Karari esya_tanimi Patch")
    logger.info(f"Mod: {'DRY-RUN (yazma yok)' if dry_run else 'GERCEK YAZMA'}")
    logger.info("TGTC tablolari (tgtc_gtip, tgtc_rules, tgtc_notes) KESINLIKLE DOKUNULMAYACAK")
    logger.info("=" * 60)

    with engine.connect() as conn:
        # 1. gumruk_emsal_kararlar
        f1, u1 = fix_table(
            conn, "gumruk_emsal_kararlar",
            id_col="id", gtip_col="gtip_kodu",
            desc_col="esya_tanimi", gerekce_col="hukuki_gerekce",
            dry_run=dry_run
        )

        # 2. gumruk_siniflandirma_kararlari
        f2, u2 = fix_table(
            conn, "gumruk_siniflandirma_kararlari",
            id_col="id", gtip_col="gtip_kodu",
            desc_col="esya_tanimi", gerekce_col="hukuki_gerekce",
            dry_run=dry_run
        )

        if not dry_run:
            conn.commit()
            logger.info(f"\nCOMMIT TAMAMLANDI -- Toplam {f1+f2} kayit guncellendi, {u1+u2} fallback yazildi")
        else:
            logger.info(f"\n[DRY-RUN] {f1+f2} kayit guncellenecekti, {u1+u2} fallback.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Cloud SQL esya_tanimi in-place duzeltici")
    parser.add_argument("--apply", action="store_true",
                        help="Gercekten yaz (varsayilan: dry-run)")
    args = parser.parse_args()
    run_patch(dry_run=not args.apply)
