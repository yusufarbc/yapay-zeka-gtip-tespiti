"""Analysis request validation and HITL state transition regressions (offline)."""
from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from api import main
from api.config import settings
from api.graph.workflow import workflow_engine
from api.schemas.product import GTIPCandidate, GTIPDecision, ProductFeatures


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "USE_GCP_EMULATOR", True)
    return TestClient(main.app)


@pytest.mark.parametrize("endpoint,kwargs", [
    ("/api/v1/analyze-json", {"json": {"product_description": "ürün"}}),
    ("/api/v1/analyze", {"data": {"product_description": "ürün"}}),
    ("/api/v1/hitl/respond", {"json": {"session_id": "s", "question_id": "q", "selected_option_id": "OPT_YES"}}),
    ("/api/v1/analyze/stream", {"params": {"product_description": "ürün"}}),
    ("/api/v1/generate-upload-url", {"params": {"filename": "photo.png"}}),
])
def test_analysis_endpoints_preserve_unauthorized_status(client, monkeypatch, endpoint, kwargs):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_PUBLIC_DEMO_ACCESS", False)
    method = "GET" if "params" in kwargs else "POST"
    assert client.request(method, endpoint, **kwargs).status_code == 401


@pytest.mark.parametrize("description", ["   ", "ab", "x" * 5001])
@pytest.mark.parametrize("mode", ["json", "multipart", "batch", "stream"])
def test_invalid_description_never_starts_analysis(client, monkeypatch, description, mode):
    start = AsyncMock()
    monkeypatch.setattr(workflow_engine, "start_analysis_async", start)
    if mode == "json":
        response = client.post("/api/v1/analyze-json", json={"product_description": description})
    elif mode == "multipart":
        response = client.post("/api/v1/analyze", data={"product_description": description})
    elif mode == "batch":
        response = client.post("/api/v1/analyze/batch", json={"product_descriptions": ["valid product", description]})
    else:
        response = client.get("/api/v1/analyze/stream", params={"product_description": description})
    assert response.status_code == 422
    start.assert_not_called()


def test_json_description_is_trimmed(client, monkeypatch):
    start = AsyncMock(return_value=GTIPDecision(session_id="s", status="MANUAL_REVIEW_REQUIRED"))
    monkeypatch.setattr(workflow_engine, "start_analysis_async", start)
    response = client.post("/api/v1/analyze-json", json={"product_description": "  valid product  "})
    assert response.status_code == 200
    start.assert_awaited_once_with(raw_text="valid product", image_uri=None)


def test_unsupported_upload_remains_a_client_error(client):
    response = client.post("/api/v1/analyze", data={"product_description": "valid product"},
                           files={"image": ("script.js", b"alert(1)", "text/javascript")})
    assert response.status_code == 400


def test_upload_destinations_do_not_collide(client):
    first = client.get("/api/v1/generate-upload-url", params={"filename": "photo.png"})
    second = client.get("/api/v1/generate-upload-url", params={"filename": "photo.png"})
    assert first.status_code == second.status_code == 200
    assert first.json()["destination"] != second.json()["destination"]


@pytest.fixture
def hitl_state(monkeypatch):
    candidate = GTIPCandidate(gtip_code="6403.51.05.00.00", chapter="64", heading="6403",
                              description="Deri ayakkabı", score=0.86)
    state = {
        "status": "WAITING_FOR_USER",
        "product_features": ProductFeatures(product_name="Deri ayakkabı", primary_material="Deri",
                                              intended_use="Ayakkabı").model_dump(),
        "selected_gtip": candidate.gtip_code,
        "candidates": [candidate.model_dump()],
        "hitl_question": {"question_id": "current-question", "options": [
            {"option_id": "OPT_YES", "impact_data": {"confirmed": "true"}},
            {"option_id": "OPT_NO", "impact_data": {"confirmed": "false"}},
        ]},
    }
    monkeypatch.setattr(main.local_state_store, "get_state", lambda _: deepcopy(state))
    save = Mock(side_effect=lambda _, updated: state.update(deepcopy(updated)))
    monkeypatch.setattr(main.local_state_store, "save_state", save)
    return state, save


@pytest.mark.parametrize("question_id,option_id", [("old-question", "OPT_YES"), ("current-question", "FORGED_YES")])
def test_stale_or_invalid_hitl_response_is_rejected(client, hitl_state, question_id, option_id):
    response = client.post("/api/v1/hitl/respond", json={"session_id": "s", "question_id": question_id,
                                                       "selected_option_id": option_id})
    assert response.status_code == 409
    hitl_state[1].assert_not_called()


def test_negative_hitl_response_requires_review_and_is_not_logged_as_approved(client, monkeypatch, hitl_state):
    log = Mock()
    learn = Mock()
    monkeypatch.setattr(main.audit_logger, "log_decision", log)
    monkeypatch.setattr(main, "append_continuous_learning_record", learn)
    payload = {"session_id": "s", "question_id": "current-question", "selected_option_id": "OPT_NO"}
    response = client.post("/api/v1/hitl/respond", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "MANUAL_REVIEW_REQUIRED"
    assert hitl_state[0]["status"] == "MANUAL_REVIEW_REQUIRED"
    assert hitl_state[0]["product_features"]["technical_specifications"]["confirmed"] == "false"
    log.assert_not_called()
    learn.assert_not_called()
    assert client.post("/api/v1/hitl/respond", json=payload).status_code == 409


def test_affirmative_hitl_response_preserves_completion(hitl_state):
    decision = workflow_engine.resume_analysis("s", "OPT_YES", question_id="current-question")
    assert decision.status == "COMPLETED"
    assert decision.gtip_code == hitl_state[0]["selected_gtip"]
    assert hitl_state[0]["hitl_question"] is None
