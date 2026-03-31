from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path

from docx import Document
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
    file: UploadFile | None = File(default=None),
    raw_text: str | None = Form(default=None),
    mode: str = Form("rewrite"),
    topic_hint: str | None = Form(default=None),
    preserve_terms: str | None = Form(default=None),
    model_name: str | None = Form(default=None),
    enable_reasoning: bool = Form(default=False),
):
    if mode not in {"analyze", "rewrite", "deep_rewrite"}:
        raise HTTPException(status_code=400, detail="mode must be analyze, rewrite, or deep_rewrite")

    has_file = file is not None and bool(file.filename)
    text_payload = (raw_text or "").strip()

    if not has_file and not text_payload:
        raise HTTPException(status_code=400, detail="either .docx file or raw_text is required")

    if has_file and not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="only .docx is supported when uploading file")

    upload_id = str(uuid.uuid4())
    upload_dir = settings.workdir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{upload_id}.docx"

    source_name = file.filename if has_file and file else "pasted-text"
    logger.info("create_run called | mode=%s | source=%s", mode, source_name)

    if has_file and file:
        with target.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    else:
        doc = Document()
        lines = [line.strip() for line in text_payload.splitlines() if line.strip()]
        if not lines:
            lines = [text_payload]
        for line in lines:
            doc.add_paragraph(line)
        doc.save(str(target))

    terms = [x.strip() for x in (preserve_terms or "").split(",") if x.strip()]
    record = pipeline.create_run_record(mode)
    pipeline.update_run_options(record.run_id, model_name=model_name, enable_reasoning=enable_reasoning)
    pipeline.start_run_in_background(
        run_id=record.run_id,
        file_path=target,
        mode=mode,
        topic_hint=topic_hint,
        preserve_terms=terms,
        model_name=model_name,
        enable_reasoning=enable_reasoning,
    )

    logger.info(
        "create_run accepted | run_id=%s | status=%s | mode=%s",
        record.run_id,
        record.status,
        record.mode,
    )

    payload = {
        "run_id": record.run_id,
        "status": record.status,
        "mode": record.mode,
        "llm_model": (model_name or "").strip() or None,
        "reasoning_enabled": enable_reasoning,
        "progress_percent": record.progress_percent,
        "current_stage": record.current_stage,
        "status_url": f"/v1/runs/{record.run_id}/status",
        "report_url": f"/v1/runs/{record.run_id}/report",
        "result_url": f"/v1/runs/{record.run_id}/result" if mode in {"rewrite", "deep_rewrite"} else None,
    }
    return payload


@router.get("/runs")
async def list_runs(limit: int = 20):
    records = pipeline.list_records(limit=max(1, min(limit, 200)))
    return {
        "total": len(records),
        "tasks": [
            {
                "run_id": r.run_id,
                "mode": r.mode,
                "status": r.status,
                "progress_percent": r.progress_percent,
                "current_stage": r.current_stage,
                "current_chunk": r.current_chunk,
                "total_chunks": r.total_chunks,
                "eta_seconds": r.eta_seconds,
                "llm_model": r.llm_model,
                "reasoning_enabled": r.reasoning_enabled,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in records
        ],
    }


@router.get("/runs/{run_id}/status")
async def get_status(run_id: str):
    record = pipeline.get_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="run not found")

    return {
        "run_id": record.run_id,
        "mode": record.mode,
        "status": record.status,
        "progress_percent": record.progress_percent,
        "current_stage": record.current_stage,
        "current_chunk": record.current_chunk,
        "total_chunks": record.total_chunks,
        "eta_seconds": record.eta_seconds,
        "llm_model": record.llm_model,
        "reasoning_enabled": record.reasoning_enabled,
        "message": record.message,
        "error": record.error,
        "report_url": f"/v1/runs/{record.run_id}/report",
        "result_url": f"/v1/runs/{record.run_id}/result" if record.mode in {"rewrite", "deep_rewrite"} else None,
    }


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str):
    record = pipeline.cancel_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="run not found")

    return {
        "run_id": record.run_id,
        "status": record.status,
        "current_stage": record.current_stage,
        "message": record.message,
    }


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


@router.get("/health/translation")
async def translation_health() -> dict:
    available, reason = pipeline.back_translator.config_status()
    return {
        "status": "ok" if available else "degraded",
        "provider": "azure_translator",
        "available": available,
        "reason": reason,
        "translation_chain": pipeline.back_translator.translation_chain(),
        "requires_region": settings.azure_translator_require_region,
    }
