from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from qnu_copilot.domain.enums import (
    GenericStatus,
    ReferenceSourceMode,
    ReferenceStatus,
    WorkflowStage,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectInfo(BaseModel):
    title: str
    core_idea: str
    discipline: str | None = None
    keywords: list[str] = Field(default_factory=list)
    need_reference_recommendation: bool = True
    minimum_total_words: int | None = None

    @field_validator("title", "core_idea")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field must not be empty")
        return normalized


class BibtexEntry(BaseModel):
    key: str | None = None
    raw_text: str
    title: str | None = None

    @field_validator("raw_text")
    @classmethod
    def validate_raw_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("raw_text must not be empty")
        return normalized


class RecommendedReferenceItem(BaseModel):
    source_index: int
    title: str
    language: str
    download_url: str
    venue: str | None = None
    year: int | None = None
    impact_note: str | None = None
    bibtex_key: str | None = None
    status: ReferenceStatus = ReferenceStatus.PENDING

    @field_validator("title", "download_url", "language")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field must not be empty")
        return normalized


class ProcessedReferenceItem(BaseModel):
    effective_index: int
    source_index: int | None = None
    title: str
    normalized_title: str
    language: str | None = None
    raw_pdf_path: str
    processed_pdf_path: str
    file_size: int
    sha256: str
    bibtex_key: str | None = None


class ReferencesState(BaseModel):
    source_mode: ReferenceSourceMode | None = None
    minimum_required: int = 20
    recommended_items: list[RecommendedReferenceItem] = Field(default_factory=list)
    bibtex_entries: list[BibtexEntry] = Field(default_factory=list)
    processed_items: list[ProcessedReferenceItem] = Field(default_factory=list)
    next_sequence: int = 1


class OutlineState(BaseModel):
    system_prompt_version: str = "outline-v1"
    user_prompt_text: str = ""
    raw_ai_text: str = ""
    normalized_json: dict[str, Any] | None = None
    confirmed_tree: dict[str, Any] | None = None
    status: GenericStatus = GenericStatus.PENDING


class ChunkPlanState(BaseModel):
    system_prompt_version: str = "chunk-plan-v1"
    user_prompt_text: str = ""
    raw_ai_text: str = ""
    normalized_json: dict[str, Any] | None = None
    confirmed_plan: dict[str, Any] | None = None
    status: GenericStatus = GenericStatus.PENDING


class GeneratedBlockState(BaseModel):
    block_index: int
    block_title: str
    raw_ai_text: str = ""
    normalized_json: dict[str, Any] | None = None
    compressed_context_raw_ai_text: str = ""
    compressed_context_json: dict[str, Any] | None = None
    status: GenericStatus = GenericStatus.PENDING


class GenerationState(BaseModel):
    current_block_index: int = 0
    total_blocks: int = 0
    blocks: list[GeneratedBlockState] = Field(default_factory=list)
    latest_compressed_context: dict[str, Any] | None = None
    abstract_raw_ai_text: str = ""
    abstract_json: dict[str, Any] | None = None
    abstract_status: GenericStatus = GenericStatus.PENDING
    status: GenericStatus = GenericStatus.PENDING


class ExportHistoryItem(BaseModel):
    output_path: str
    exported_at: str
    reference_count: int
    log_path: str = ""


class ExportState(BaseModel):
    last_docx_path: str = ""
    last_exported_at: str = ""
    status: GenericStatus = GenericStatus.PENDING
    history: list[ExportHistoryItem] = Field(default_factory=list)


class UIState(BaseModel):
    last_route: str = ""
    notices_dismissed: list[str] = Field(default_factory=list)


class ProjectState(BaseModel):
    schema_version: str = "1.0"
    project_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    template_id: str = "qnu-undergraduate-v1"
    workflow_stage: WorkflowStage = WorkflowStage.REFERENCES
    project: ProjectInfo
    references: ReferencesState = Field(default_factory=ReferencesState)
    outline: OutlineState = Field(default_factory=OutlineState)
    chunk_plan: ChunkPlanState = Field(default_factory=ChunkPlanState)
    generation: GenerationState = Field(default_factory=GenerationState)
    export: ExportState = Field(default_factory=ExportState)
    ui: UIState = Field(default_factory=UIState)

    def touch(self) -> None:
        self.updated_at = utc_now()
