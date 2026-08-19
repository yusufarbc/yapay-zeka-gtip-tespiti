"""
Unit and integration tests for TGTC 2026 Seed and Dynamic Customs ETL pipeline.
Verifies tgtc_gtip tree, tgtc_notes, tgtc_rules, and BTBExtraction schema.
"""

import pytest
import os
import json
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session

from api.db.database import (
    engine, init_orm_tables, SessionLocal,
    TgtcGtipModel, TgtcNoteModel, TgtcRuleModel, GumrukSiniflandirmaKarariModel
)
from scripts.seed_tgtc_2026 import (
    seed_gir_and_auxiliary_rules,
    seed_chapter_notes_and_exclusions,
    seed_gtip_tree,
    run_full_seed
)


class BTBExtraction(BaseModel):
    karar_tipi: str = Field(description="SINIFLANDIRMA_KARARI veya BTB")
    referans_no: str
    gtip_kodu: str
    yayin_tarihi: str
    resmi_gazete_sayisi: str
    esya_tanimi: str
    hukuki_gerekce: str
    valid_until: Optional[str] = "2099-12-31"


def test_seed_gir_and_rules():
    """GİR 1-6 kurallarının ve ölçü birimlerinin veritabanına aktarıldığını doğrular."""
    init_orm_tables()
    with SessionLocal() as session:
        seed_gir_and_auxiliary_rules(session)
        
        gir_rules = session.query(TgtcRuleModel).filter_by(rule_type="GIR").all()
        assert len(gir_rules) >= 6
        
        rule_numbers = [r.rule_number for r in gir_rules]
        assert "1" in rule_numbers
        assert "3(a)" in rule_numbers
        assert "6" in rule_numbers

        # Ölçü birimleri veya açıklamalar
        all_rules = session.query(TgtcRuleModel).all()
        assert len(all_rules) >= 10


def test_seed_chapter_notes_and_exclusions():
    """97 fasıl notunun ve dışlama hükümlerinin (EXCLUSION) ayrıştırıldığını doğrular."""
    init_orm_tables()
    with SessionLocal() as session:
        seed_chapter_notes_and_exclusions(session, generate_embeddings=False)
        
        notes = session.query(TgtcNoteModel).all()
        assert len(notes) >= 90
        
        # En az bir fasılda dışlama notu olmalı
        exclusions = session.query(TgtcNoteModel).filter_by(note_type="EXCLUSION").all()
        assert len(exclusions) > 0
        
        # Fasıl 64 veya 42 notu mevcut mu?
        f64 = session.query(TgtcNoteModel).filter_by(chapter_code="64").first()
        assert f64 is not None


def test_seed_gtip_tree_hierarchy():
    """TGTC GTİP ağacının (CHAPTER, HEADING, SUBHEADING, GTIP) hiyerarşik bağlandığını doğrular."""
    init_orm_tables()
    with SessionLocal() as session:
        seed_gtip_tree(session, generate_embeddings=False)
        
        total_gtips = session.query(TgtcGtipModel).count()
        assert total_gtips > 1000
        
        # Fasıl 01 kaydı
        chap_01 = session.query(TgtcGtipModel).filter_by(gtip_code="01").first()
        assert chap_01 is not None
        assert chap_01.level == "CHAPTER"
        assert chap_01.parent_code is None
        
        # Pozisyon 0101 kaydı
        head_0101 = session.query(TgtcGtipModel).filter_by(gtip_code="0101").first()
        assert head_0101 is not None
        assert head_0101.level == "HEADING"
        assert head_0101.parent_code == "01"


def test_btb_extraction_pydantic_schema():
    """Gemini 3.5 Flash Lite için BTBExtraction veri şemasını doğrular."""
    mock_payload = {
        "karar_tipi": "SINIFLANDIRMA_KARARI",
        "referans_no": "TR-2026-00142",
        "gtip_kodu": "8507.60.00.00.00",
        "yayin_tarihi": "2026-01-15",
        "resmi_gazete_sayisi": "33120",
        "esya_tanimi": "5.5 inç ekranlı lityum bataryalı akıllı cep telefonu",
        "hukuki_gerekce": "GİR 1 ve GİR 6 uyarınca 8507 pozisyonu kapsamında değerlendirilmiştir.",
        "valid_until": "2099-12-31"
    }
    obj = BTBExtraction(**mock_payload)
    assert obj.gtip_kodu == "8507.60.00.00.00"
    assert obj.karar_tipi == "SINIFLANDIRMA_KARARI"
    assert obj.valid_until == "2099-12-31"
