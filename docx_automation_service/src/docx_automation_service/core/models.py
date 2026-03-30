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


class RunMode(BaseModel):
    mode: Literal["analyze", "rewrite"]


class RunRecord(BaseModel):
    run_id: str
    mode: Literal["analyze", "rewrite"]
    status: Literal["running", "done", "failed"]
    report_path: Path
    result_path: Path | None = None
    error: str | None = None
