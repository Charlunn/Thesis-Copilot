from pathlib import Path
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class ChunkRef(BaseModel):
    block_type: Literal["paragraph", "table_cell"]
    paragraph_index: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    cell_index: int | None = None
    style_name: str | None = None
    is_heading: bool = False
    is_reference_section: bool = False


class Chunk(BaseModel):
    chunk_id: str
    text: str
    ref: ChunkRef


class ChunkRisk(BaseModel):
    chunk_id: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    aigc_score: float = Field(ge=0.0, le=1.0)
    flagged: bool
    # Layer 3 metrics (populated in deep_rewrite mode)
    burstiness_score: float | None = None
    layer3_risk_score: float | None = None


class RunMode(BaseModel):
    mode: Literal["analyze", "rewrite", "deep_rewrite"]


class LayerReport(BaseModel):
    """Summary of work performed by one processing layer."""

    layer: int
    name: str
    chunks_processed: int
    chunks_skipped: int
    available: bool
    """False when the layer's external dependency (e.g. DeepL API key) is absent."""


class RunRecord(BaseModel):
    run_id: str
    mode: Literal["analyze", "rewrite", "deep_rewrite"]
    status: Literal["queued", "running", "done", "failed", "canceled"]
    report_path: Path
    result_path: Path | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None
    current_stage: str = "queued"
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    current_chunk: int = 0
    total_chunks: int = 0
    eta_seconds: int | None = None
    llm_model: str | None = None
    reasoning_enabled: bool = False
    message: str | None = None
    error: str | None = None
    # Per-layer processing summaries (populated for deep_rewrite mode)
    layer_reports: list[LayerReport] = Field(default_factory=list)
