"""
GCP us-central1 ve Yeni Mimari Birim Testleri.
gcp_architecture_report.md şartnamesi doğrultusunda eklenen bileşenlerin testleri:
1. Vertex AI Merkezi İstemci ve text-embedding-005 üretimi
2. İki Aşamalı FastMCP Hukuki Arama Protokolü
3. AlloyDB / Cloud SQL Dinamik Kural Tablosu ve HITL Denetimi
4. LangGraph CustomsState ve İş Akışı
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from api.config import settings
from api.db.database import (
    init_orm_tables, SessionLocal, GumrukMevzuatMaddesiModel,
    GtipRuleModel, EmsalBtbKarariModel
)
from api.modules.vertex_client import get_genai_client, generate_embedding
from api.modules.mcp_customs_tools import (
    mcp_customs_tools, execute_search_customs_articles, execute_fetch_exact_article_by_id
)
from api.graph.workflow import check_dynamic_gtip_rules, build_customs_workflow
from api.graph.state import CustomsState

def test_config_us_central1_defaults():
    """GCP_REGION varsayılanının us-central1 ve projenin gumruk-mevzuat olduğunu doğrular."""
    assert settings.GCP_REGION == "us-central1"
    assert settings.GCP_PROJECT_ID == "gumruk-mevzuat"
    assert settings.EMBEDDING_MODEL == "text-embedding-005"
    assert settings.VECTOR_DIM == 768

def test_database_models_and_init():
    """Yeni mimarideki 3 ana tablonun (mevzuat, gtip_rules, emsal_btb) oluşturulduğunu doğrular."""
    init_orm_tables()
    with SessionLocal() as session:
        # gtip_rules başlangıç tohumlarını kontrol et
        rules_count = session.query(GtipRuleModel).count()
        assert rules_count >= 1

        # 8471 kuralını kontrol et
        rule_8471 = session.query(GtipRuleModel).filter(GtipRuleModel.parent_heading == "8471").first()
        assert rule_8471 is not None
        assert rule_8471.parametre_adi in ["weight", "has_display_and_keyboard"]

def test_dynamic_gtip_rules_checker():
    """Eksik parametre durumunda Dinamik Kural Denetçisinin soru döndürdüğünü doğrular."""
    # 1. Eksik parametre: specs boş
    res = check_dynamic_gtip_rules("8471", {})
    assert res is not None
    assert "missing_parameter" in res
    assert res["missing_parameter"] in ["weight", "has_display_and_keyboard"]
    assert "question" in res
    assert len(res["options"]) >= 2

    # 2. Parametre sağlandıysa
    satisfied_specs = {"weight": "5kg", "has_display_and_keyboard": "true"}
    res2 = check_dynamic_gtip_rules("8471", satisfied_specs)
    assert res2 is None

def test_mcp_customs_tools_definitions():
    """İki aşamalı FastMCP araç deklarasyonlarının doğruluğunu test eder."""
    assert len(mcp_customs_tools) == 1
    decls = mcp_customs_tools[0].function_declarations
    tool_names = [d.name for d in decls]
    assert "search_customs_articles" in tool_names
    assert "fetch_exact_article_by_id" in tool_names

def test_mcp_customs_tools_execution():
    """Keşif ve Kesin Getirme fonksiyonlarının veritabanı ile çalışmasını test eder."""
    with SessionLocal() as session:
        test_article = GumrukMevzuatMaddesiModel(
            tarih="2026-09-07",
            resmi_gazete_sayisi=33100,
            kanun_no="4458",
            madde_kodu="MADDE 15",
            madde_metni="Gümrük tarifesi, eşyanın gümrük vergisine tabi tutulmasında esas alınır.",
            kaynak_url="https://resmigazete.gov.tr/eskiler/2026/09/20260907-1.htm",
            icerik_vektor=None
        )
        session.add(test_article)
        session.commit()
        article_id = test_article.id

        # Aşama 1: Keşif
        search_res = execute_search_customs_articles("Gümrük tarifesi", session)
        assert isinstance(search_res, list)

        # Aşama 2: Kesin Getirme
        fetch_res = execute_fetch_exact_article_by_id(article_id, session)
        assert "error" not in fetch_res
        assert fetch_res["kanun_no"] == "4458"
        assert fetch_res["madde_kodu"] == "MADDE 15"
        assert "Gümrük tarifesi" in fetch_res["ham_metin"]

def test_langgraph_workflow_compilation():
    """LangGraph StateGraph iş akışının hatasız derlendiğini doğrular."""
    wf = build_customs_workflow()
    assert wf is not None
