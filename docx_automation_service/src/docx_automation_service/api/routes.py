from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from docx_automation_service.core.config import settings
from docx_automation_service.integrations.mock_detectors import (
    HeuristicAIGCDetector,
    HeuristicSimilarityDetector,
)
from docx_automation_service.integrations.siliconflow_rewriter import SiliconFlowRewriter
from docx_automation_service.services.pipeline import PipelineService

router = APIRouter(prefix="/v1", tags=["pipeline"])
logger = logging.getLogger(__name__)

pipeline = PipelineService(
    similarity_detector=HeuristicSimilarityDetector(),
    aigc_detector=HeuristicAIGCDetector(),
    rewriter=SiliconFlowRewriter(),
)


@router.post("/runs")
async def create_run(
    file: UploadFile = File(...),
    mode: str = Form("rewrite"),
    topic_hint: str | None = Form(default=None),
    preserve_terms: str | None = Form(default=None),
):
    if mode not in {"analyze", "rewrite", "deep_rewrite"}:
        raise HTTPException(status_code=400, detail="mode must be analyze, rewrite, or deep_rewrite")

    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="only .docx is supported")

    upload_id = str(uuid.uuid4())
    upload_dir = settings.workdir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{upload_id}.docx"

    logger.info("create_run called | mode=%s | filename=%s", mode, file.filename)

    with target.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    terms = [x.strip() for x in (preserve_terms or "").split(",") if x.strip()]
    record = await pipeline.run(target, mode=mode, topic_hint=topic_hint, preserve_terms=terms)

    logger.info(
        "create_run finished | run_id=%s | status=%s | mode=%s",
        record.run_id,
        record.status,
        record.mode,
    )

    payload = {
        "run_id": record.run_id,
        "status": record.status,
        "mode": record.mode,
        "report_url": f"/v1/runs/{record.run_id}/report",
        "result_url": f"/v1/runs/{record.run_id}/result" if mode in {"rewrite", "deep_rewrite"} else None,
    }
    return payload


@router.get("/runs/{run_id}/report")
async def get_report(run_id: str):
    logger.info("get_report called | run_id=%s", run_id)
    record = pipeline.get_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="run not found")

    if not record.report_path.exists():
        raise HTTPException(status_code=404, detail="report not ready")

    return json.loads(record.report_path.read_text(encoding="utf-8"))


@router.get("/runs/{run_id}/result")
async def get_result(run_id: str):
    logger.info("get_result called | run_id=%s", run_id)
    record = pipeline.get_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="run not found")

    if record.mode not in {"rewrite", "deep_rewrite"}:
        raise HTTPException(status_code=400, detail="result only exists for rewrite and deep_rewrite modes")

    if not record.result_path or not Path(record.result_path).exists():
        raise HTTPException(status_code=404, detail="result not ready")

    return FileResponse(
        path=str(record.result_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"rewritten-{run_id}.docx",
    )
