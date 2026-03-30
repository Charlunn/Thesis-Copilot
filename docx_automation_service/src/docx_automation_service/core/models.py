from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ChunkRef(BaseModel):
    block_type: Literal["paragraph", "table_cell"]
    paragraph_index: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    cell_index: int | None = None


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
    status: Literal["running", "done", "failed"]
    report_path: Path
    result_path: Path | None = None
    error: str | None = None
    # Per-layer processing summaries (populated for deep_rewrite mode)
    layer_reports: list[LayerReport] = Field(default_factory=list)
