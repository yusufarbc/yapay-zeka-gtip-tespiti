import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.database import (
    Base, TgtcGtipVersionModel, calculate_dynamic_candidate_score,
    upsert_tgtc_temporal_version,
)
from api.modules.discriminator_engine import DiscriminatorExtractor
from api.modules.discriminator_engine import DiscriminatorQuestion
from api.modules.rag_engine import HierarchicalSearchResult
from scripts.extract_official_gazette_exact import parse_customs_table_matrix
from scripts.scrape_all_btb_2020_2026 import iter_month_windows


def test_btb_score_is_not_diluted_when_no_verified_precedent_exists():
    assert calculate_dynamic_candidate_score(0.87, btb_support=0.0, verified_btb_count=0) == 0.87
    assert calculate_dynamic_candidate_score(0.80, btb_support=0.90, verified_btb_count=1) == 0.86


def test_close_branches_create_bounded_multiple_choice_question():
    question = DiscriminatorExtractor().extract("session-1", [
        {"gtip_code": "8517", "description": "Telefon cihazları", "similarity_score": 0.91},
        {"gtip_code": "8524", "description": "Dokunmatik düz panel modülleri", "similarity_score": 0.85},
    ])
    assert question is not None
    assert question.target_branches == {"0": "8517", "1": "8524", "2": ""}
    assert question.options[-1] == "Bilinmiyor"


def test_score_gap_at_threshold_does_not_interrupt():
    question = DiscriminatorExtractor().extract("session-1", [
        {"gtip_code": "8517", "description": "Telefon", "similarity_score": 0.91},
        {"gtip_code": "8524", "description": "Panel", "similarity_score": 0.83},
    ])
    assert question is None


def test_month_windows_cover_range_without_overlap():
    windows = list(iter_month_windows(dt.date(2020, 1, 15), dt.date(2020, 3, 4)))
    assert [(item.start, item.end) for item in windows] == [
        (dt.date(2020, 1, 15), dt.date(2020, 1, 31)),
        (dt.date(2020, 2, 1), dt.date(2020, 2, 29)),
        (dt.date(2020, 3, 1), dt.date(2020, 3, 4)),
    ]


def test_structured_gazette_matrix_preserves_columns():
    items = parse_customs_table_matrix([
        ["Karar No", "Eşya Tanımı", "GTİP", "Hukuki Gerekçe"],
        ["1", "Paslanmaz çelik elektrikli su ısıtıcısı", "8516.79.70.00.00", "GİR 1 ve GİR 6"],
    ], "2026-01-01", "33000")
    assert len(items) == 1
    assert items[0].gtip_kodu == "851679700000"
    assert items[0].hukuki_gerekce == "GİR 1 ve GİR 6"


def test_changed_tariff_row_closes_previous_version_instead_of_deleting_it():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        upsert_tgtc_temporal_version(
            session, gtip_code="851679700000", description="Eski tanım",
            effective_from="2026-01-01", source_gazette_no="33000",
        )
        session.commit()
        upsert_tgtc_temporal_version(
            session, gtip_code="851679700000", description="Yeni tanım",
            effective_from="2026-07-01", source_gazette_no="33100",
        )
        session.commit()
        versions = session.query(TgtcGtipVersionModel).order_by(
            TgtcGtipVersionModel.gecerlilik_baslangic
        ).all()
        assert len(versions) == 2
        assert versions[0].gecerlilik_bitis == "2026-06-30"
        assert versions[1].gecerlilik_bitis is None


def test_discriminator_resume_continues_from_stored_features(monkeypatch):
    from api.graph.workflow import workflow_engine
    from api.db.gcp_emulator import local_state_store
    from api.modules.feature_extractor import feature_extractor
    from api.modules.rag_engine import rag_engine

    state = {
        "session_id": "s1",
        "raw_text": "akıllı telefon",
        "image_uri": None,
        "product_features": {
            "product_name": "akıllı telefon", "primary_material": "metal",
            "intended_use": "haberleşme", "technical_specifications": {},
        },
        "allowed_chapters": ["85"],
        "applied_gir_rules": ["GİR 1"],
        "status": "WAITING_FOR_USER",
        "selected_gtip": None,
        "candidates": [],
        "hitl_question": {
            "question_id": "disc_tarife_dali_s1",
            "question_text": "Hangi dal?",
            "missing_parameter": "tarife_dali",
            "options": [
                {"option_id": "DISC_0", "text": "8517", "impact_data": {"selected_branch": "8517"}},
                {"option_id": "DISC_1", "text": "8524", "impact_data": {"selected_branch": "8524"}},
            ],
        },
        "discriminator_traversal": {"pending_level": "HEADING", "retained_chapters": ["85"]},
    }
    monkeypatch.setattr(local_state_store, "get_state", lambda _session_id: state)
    monkeypatch.setattr(local_state_store, "save_state", lambda _session_id, new_state: state.update(new_state))
    monkeypatch.setattr(feature_extractor, "extract_features", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("yeniden çıkarım yapılmamalı")))
    next_question = DiscriminatorQuestion(
        session_id="s1", parameter_name="alt_pozisyon", question_text="Hangi alt pozisyon?",
        options=["851711", "851713", "Bilinmiyor"],
        target_branches={"0": "851711", "1": "851713", "2": ""},
    )
    monkeypatch.setattr(rag_engine, "search_candidates_hierarchical", lambda **_kwargs: HierarchicalSearchResult(
        discriminator_question=next_question,
        traversal_state={"pending_level": "SUBHEADING", "locked_heading": "8517", "branches": [
            {"gtip_code": "851711", "description": "Birinci dal"},
            {"gtip_code": "851713", "description": "İkinci dal"},
        ]},
    ))

    decision = workflow_engine.resume_analysis("s1", "DISC_0", question_id="disc_tarife_dali_s1")
    assert decision.status == "WAITING_FOR_USER"
    assert decision.hitl_question.missing_parameter == "alt_pozisyon"
