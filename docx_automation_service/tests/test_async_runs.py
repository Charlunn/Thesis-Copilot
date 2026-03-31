from __future__ import annotations

import io
import time

from docx import Document
from fastapi.testclient import TestClient

from docx_automation_service.main import app


def _make_docx_bytes(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_async_run_status_progress_and_report() -> None:
    client = TestClient(app)
    files = {
        "file": (
            "demo.docx",
            _make_docx_bytes("这是一段用于异步任务测试的正文内容。"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    data = {"mode": "analyze"}

    resp = client.post("/v1/runs", files=files, data=data)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "queued"
    assert payload["status_url"].endswith("/status")

    run_id = payload["run_id"]

    final = None
    for _ in range(60):
        status_resp = client.get(f"/v1/runs/{run_id}/status")
        assert status_resp.status_code == 200
        status_payload = status_resp.json()
        assert 0 <= status_payload["progress_percent"] <= 100
        if status_payload["status"] in {"done", "failed"}:
            final = status_payload
            break
        time.sleep(0.1)

    assert final is not None
    assert final["status"] == "done"

    report_resp = client.get(f"/v1/runs/{run_id}/report")
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert report["run_id"] == run_id


def test_list_runs_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/v1/runs?limit=5")
    assert resp.status_code == 200
    payload = resp.json()
    assert "tasks" in payload
    assert isinstance(payload["tasks"], list)


def test_run_options_echoed_in_status() -> None:
    client = TestClient(app)
    files = {
        "file": (
            "demo.docx",
            _make_docx_bytes("用于模型选项测试。"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    data = {
        "mode": "analyze",
        "model_name": "test-model-override",
        "enable_reasoning": "false",
    }

    resp = client.post("/v1/runs", files=files, data=data)
    assert resp.status_code == 200
    payload = resp.json()
    run_id = payload["run_id"]

    status_resp = client.get(f"/v1/runs/{run_id}/status")
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["llm_model"] == "test-model-override"
    assert status["reasoning_enabled"] is False


def test_cancel_run_endpoint() -> None:
    client = TestClient(app)
    files = {
        "file": (
            "demo.docx",
            _make_docx_bytes("用于取消任务测试。"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    data = {"mode": "rewrite"}

    resp = client.post("/v1/runs", files=files, data=data)
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    cancel_resp = client.delete(f"/v1/runs/{run_id}")
    assert cancel_resp.status_code == 200
    canceled = cancel_resp.json()
    assert canceled["status"] in {"canceled", "done", "failed"}


def test_submit_raw_text_without_file() -> None:
    client = TestClient(app)
    data = {
        "mode": "analyze",
        "raw_text": "这是直接粘贴提交的测试文本。\n第二段内容。",
    }

    resp = client.post("/v1/runs", data=data)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "queued"
    assert payload["mode"] == "analyze"
