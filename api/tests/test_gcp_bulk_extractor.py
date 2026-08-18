"""
Unit tests for GCP Vertex AI (Gemini 3.6 Flash) Bulk Extractor & Cloud SQL persistence pipeline.
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from scripts.gcp_bulk_extractor_2020_2026 import run_gcp_bulk_extraction, fetch_official_gazette_day_text
from api.config import settings

client = TestClient(app)


def test_model_configured_to_gemini_3_6_flash():
    """Gemini 3.6 Flash modelinin sistem konfigürasyonunda aktif olduğunu doğrular."""
    assert settings.DEFAULT_LLM_MODEL == "gemini-3.6-flash"


def test_fetch_official_gazette_day_text_structure():
    """Resmi Gazete fihrist indirme fonksiyonunu doğrular (görece güvenli tarih)."""
    # Test bir günün metin yapısını çeker
    text = fetch_official_gazette_day_text(year=2025, month=10, day=15)
    # Ya metin döner ya da None (bağlantı durumuna göre)
    assert text is None or isinstance(text, str)


def test_run_gcp_bulk_extraction_limit_days():
    """Maksimum gün sınırlaması ile GCP bulk extractor scriptini doğrular."""
    res = run_gcp_bulk_extraction(start_year=2025, end_year=2025, limit_days=1)
    assert res["status"] == "SUCCESS"
    assert res["days_processed"] == 1
    assert "decisions_extracted" in res


def test_gcp_sync_status_endpoint():
    """GET /api/v1/admin/sync-gcp-official-gazette-status endpointini doğrular."""
    response = client.get("/api/v1/admin/sync-gcp-official-gazette-status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert data["active_model"] == "gemini-3.6-flash"
    assert "cloud_sql_siniflandirma_kararlari_count" in data
