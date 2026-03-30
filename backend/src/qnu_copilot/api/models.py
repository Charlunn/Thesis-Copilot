from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from qnu_copilot.domain.enums import SkipReason, WorkflowStage
from qnu_copilot.domain.models import ProjectState, RecommendedReferenceItem
from qnu_copilot.services.contracts import ParsedContract


class CreateProjectRequest(BaseModel):
    title: str
    core_idea: str
    discipline: str | None = None
    keywords: list[str] = Field(default_factory=list)
    need_reference_recommendation: bool = True
    minimum_total_words: int | None = None
    minimum_required_references: int = 20
    template_id: str = "qnu-undergraduate-v1"


class ProjectStateResponse(BaseModel):
    project_id: str
    project_root: str
    state_path: str
    workflow_stage: WorkflowStage
    state: ProjectState


class ProjectListItem(BaseModel):
    project_id: str
    title: str
    workflow_stage: WorkflowStage
    updated_at: str
    project_root: str
    state_path: str
    need_reference_recommendation: bool
    processed_pdf_count: int
    recommended_reference_count: int


class ProjectListResponse(BaseModel):
    projects: list[ProjectListItem]


class RecommendationImportRequest(BaseModel):
    raw_text: str


class RecommendationImportResult(BaseModel):
    project_id: str
    project_root: str
    state_path: str
    workflow_stage: WorkflowStage
    imported_count: int
    zh_count: int
    en_count: int
    parse_result: ParsedContract
    state: ProjectState


class OutlineImportRequest(BaseModel):
    raw_text: str


class OutlineImportResult(BaseModel):
    project_id: str
    project_root: str
    state_path: str
    workflow_stage: WorkflowStage
    parse_result: ParsedContract
    state: ProjectState


class OutlineConfirmRequest(BaseModel):
    outline_tree: dict[str, Any]


class ChunkPlanImportRequest(BaseModel):
    raw_text: str


class ChunkPlanImportResult(BaseModel):
    project_id: str
    project_root: str
    state_path: str
    workflow_stage: WorkflowStage
    parse_result: ParsedContract
    state: ProjectState


class ChunkPlanConfirmRequest(BaseModel):
    chunk_plan: dict[str, Any]


class SkipReferenceRequest(BaseModel):
    reason: SkipReason


class SkipReferenceResponse(BaseModel):
    project_id: str
    source_index: int
    status: str
    workflow_stage: WorkflowStage
    item: RecommendedReferenceItem


class ReferencePdfImportRequest(BaseModel):
    pdf_path: str


class ProcessedReferencePayload(BaseModel):
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


class ProcessedReferenceResponse(BaseModel):
    project_id: str
    workflow_stage: WorkflowStage
    item: ProcessedReferencePayload


class BatchPdfImportRequest(BaseModel):
    pdf_paths: list[str]


class BatchReviewItem(BaseModel):
    file_path: str
    reason: str


class BatchImportResult(BaseModel):
    project_id: str
    project_root: str
    state_path: str
    workflow_stage: WorkflowStage
    processed_items: list[ProcessedReferencePayload]
    review_items: list[BatchReviewItem]
    state: ProjectState


class BibtexImportRequest(BaseModel):
    raw_text: str


class BibtexImportResult(BaseModel):
    project_id: str
    project_root: str
    state_path: str
    workflow_stage: WorkflowStage
    imported_count: int
    state: ProjectState


class ContractParseRequest(BaseModel):
    raw_text: str
    project_id: str | None = None


class ContractParseResult(BaseModel):
    contract_type: str
    raw_text: str
    normalized_json_text: str
    parsed_object: dict[str, Any] | list[Any]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_snapshot_path: str | None = None
    normalized_snapshot_path: str | None = None


class PromptPreviewResponse(BaseModel):
    project_id: str
    prompt_name: str
    prompt_text: str
    prompt_snapshot_path: str
    workflow_stage: WorkflowStage
    model_hint: str | None = None
    instructions: list[str] = Field(default_factory=list)


class BlockImportRequest(BaseModel):
    raw_text: str


class BlockImportResult(BaseModel):
    project_id: str
    block_index: int
    workflow_stage: WorkflowStage
    parse_result: ParsedContract
    state: ProjectState


class CompressedContextImportRequest(BaseModel):
    raw_text: str


class ExportProjectRequest(BaseModel):
    output_filename: str | None = None


class ExportProjectResult(BaseModel):
    project_id: str
    workflow_stage: WorkflowStage
    output_path: str
    log_path: str
    reference_count: int
    message: str
    state: ProjectState


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
