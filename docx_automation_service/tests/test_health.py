from fastapi.testclient import TestClient

from docx_automation_service.main import app
from docx_automation_service.api.routes import pipeline


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_web_app() -> None:
    client = TestClient(app)
    resp = client.get("/app")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_translation_health() -> None:
    client = TestClient(app)
    resp = client.get("/v1/health/translation")
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["provider"] == "azure_translator"
    assert isinstance(payload["available"], bool)
    assert payload["reason"] in {"ok", "azure_translator_key_missing", "azure_translator_region_missing"}
    assert payload["translation_chain"] == pipeline.back_translator.translation_chain()
