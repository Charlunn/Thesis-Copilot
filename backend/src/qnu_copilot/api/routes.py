from __future__ import annotations

import json
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pathlib import Path

from qnu_copilot.api.config_models import (
    APIConfigResponse,
    LLMProviderConfigResponse,
    NotebookLMConfigResponse,
    ProviderStatusResponse,
    SetDefaultProviderRequest,
    UpdateNotebookLMRequest,
    UpdateProviderRequest,
)
from qnu_copilot.api.models import (
    AbstractImportRequest,
    BlockImportRequest,
    BlockImportResult,
    BatchImportResult,
    BatchPdfImportRequest,
    BatchReviewItem,
    BibtexImportRequest,
    BibtexImportResult,
    ChunkPlanConfirmRequest,
    ChunkPlanImportRequest,
    ChunkPlanImportResult,
    CompressedContextImportRequest,
    ContractParseRequest,
    ContractParseResult,
    CreateProjectRequest,
    ErrorResponse,
    ExportProjectRequest,
    ExportProjectResult,
    OutlineConfirmRequest,
    OutlineImportRequest,
    OutlineImportResult,
    PromptPreviewResponse,
    ProcessedReferencePayload,
    ProcessedReferenceResponse,
    ProjectListItem,
    ProjectListResponse,
    ProjectStateResponse,
    RecommendationImportRequest,
    RecommendationImportResult,
    ReferencePdfImportRequest,
    SkipReferenceRequest,
    SkipReferenceResponse,
)
from qnu_copilot.domain.enums import ContractType
from qnu_copilot.domain.models import ProjectInfo
from qnu_copilot.services.contracts import ContractParserService
from qnu_copilot.services.errors import AppError
from qnu_copilot.services.template_checker import TemplateChecker
from qnu_copilot.services.generation import GenerationService
from qnu_copilot.services.chunk_plan import ChunkPlanService
from qnu_copilot.services.export import ProjectExportService
from qnu_copilot.services.outline import OutlineService
from qnu_copilot.services.prompts import PromptFactoryService
from qnu_copilot.services.references import ReferenceService
from qnu_copilot.services.workspace import WorkspaceManager


def _load_prompt_metadata(prompt_type: str) -> tuple[str | None, list[str]]:
    """Load model_hint and instructions from prompt metadata files."""
    try:
        assets_root = Path(__file__).resolve().parents[3] / "assets" / "prompts"
        metadata_file = assets_root / f"{prompt_type}.json"
        if metadata_file.exists():
            with open(metadata_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("model_hint"), data.get("instructions", [])
    except Exception:
        pass
    return None, []


def _get_prompt_type(prompt_name: str) -> str:
    """Map prompt_name to prompt type for metadata lookup."""
    if "reference_recommendation" in prompt_name:
        return "reference_recommendation"
    if prompt_name == "outline_prompt":
        return "outline"
    if "chunk_plan" in prompt_name:
        return "chunk_plan"
    if "generate_prompt" in prompt_name:
        return "block_generation"
    if "compress_prompt" in prompt_name:
        return "compression"
    if prompt_name == "abstract_prompt":
        return "abstract"
    return prompt_name


def create_router(
    workspace_manager: WorkspaceManager,
    reference_service: ReferenceService,
    contract_parser: ContractParserService,
    outline_service: OutlineService,
    chunk_plan_service: ChunkPlanService,
    generation_service: GenerationService,
    prompt_factory: PromptFactoryService,
    export_service: ProjectExportService,
) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/templates/status")
    def get_template_status() -> dict[str, str | bool]:
        """Get the status of the default template."""
        checker = TemplateChecker()
        status = checker.get_default_template_status()
        return status

    @router.post("/projects", response_model=ProjectStateResponse)
    def create_project(request: CreateProjectRequest) -> ProjectStateResponse:
        state, project_root = workspace_manager.create_project(
            ProjectInfo(
                title=request.title,
                core_idea=request.core_idea,
                discipline=request.discipline,
                keywords=request.keywords,
                need_reference_recommendation=request.need_reference_recommendation,
                minimum_total_words=request.minimum_total_words,
            ),
            template_id=request.template_id,
            minimum_required_references=request.minimum_required_references,
        )
        state_path = workspace_manager.get_state_path(state.project_id)
        return ProjectStateResponse(
            project_id=state.project_id,
            project_root=str(project_root.resolve()),
            state_path=str(state_path.resolve()),
            workflow_stage=state.workflow_stage,
            state=state,
        )

    @router.get("/projects", response_model=ProjectListResponse)
    def list_projects() -> ProjectListResponse:
        projects = [
            ProjectListItem(
                project_id=state.project_id,
                title=state.project.title,
                workflow_stage=state.workflow_stage,
                updated_at=state.updated_at.isoformat(),
                project_root=str(project_root.resolve()),
                state_path=str((project_root / "state.json").resolve()),
                need_reference_recommendation=state.project.need_reference_recommendation,
                processed_pdf_count=len(state.references.processed_items),
                recommended_reference_count=len(state.references.recommended_items),
            )
            for state, project_root in workspace_manager.list_projects()
        ]
        return ProjectListResponse(projects=projects)

    @router.get("/projects/{project_id}", response_model=ProjectStateResponse)
    def get_project(project_id: str) -> ProjectStateResponse:
        state = workspace_manager.load_state(project_id)
        project_root = workspace_manager.get_project_root(project_id)
        state_path = workspace_manager.get_state_path(project_id)
        return ProjectStateResponse(
            project_id=project_id,
            project_root=str(project_root.resolve()),
            state_path=str(state_path.resolve()),
            workflow_stage=state.workflow_stage,
            state=state,
        )

    @router.post(
        "/projects/{project_id}/references/recommendations/import",
        response_model=RecommendationImportResult,
    )
    def import_recommendations(
        project_id: str,
        request: RecommendationImportRequest,
    ) -> RecommendationImportResult:
        parsed = reference_service.import_recommendations(project_id, request.raw_text)
        state = workspace_manager.load_state(project_id)
        zh_count = sum(1 for item in state.references.recommended_items if item.language == "zh")
        en_count = sum(1 for item in state.references.recommended_items if item.language == "en")
        return RecommendationImportResult(
            project_id=project_id,
            project_root=str(workspace_manager.get_project_root(project_id).resolve()),
            state_path=str(workspace_manager.get_state_path(project_id).resolve()),
            workflow_stage=state.workflow_stage,
            imported_count=len(state.references.recommended_items),
            zh_count=zh_count,
            en_count=en_count,
            parse_result=parsed,
            state=state,
        )

    @router.get(
        "/projects/{project_id}/prompts/references/recommendation",
        response_model=PromptPreviewResponse,
    )
    def get_reference_recommendation_prompt(project_id: str) -> PromptPreviewResponse:
        prompt_text, snapshot = prompt_factory.render_reference_recommendation_prompt(project_id)
        state = workspace_manager.load_state(project_id)
        model_hint, instructions = _load_prompt_metadata("reference_recommendation")
        return PromptPreviewResponse(
            project_id=project_id,
            prompt_name="reference_recommendation_prompt",
            prompt_text=prompt_text,
            prompt_snapshot_path=str(snapshot.resolve()),
            workflow_stage=state.workflow_stage,
            model_hint=model_hint,
            instructions=instructions,
        )

    @router.get(
        "/projects/{project_id}/prompts/outline",
        response_model=PromptPreviewResponse,
    )
    def get_outline_prompt(project_id: str) -> PromptPreviewResponse:
        prompt_text, snapshot = prompt_factory.render_outline_prompt(project_id)
        state = workspace_manager.load_state(project_id)
        model_hint, instructions = _load_prompt_metadata("outline")
        return PromptPreviewResponse(
            project_id=project_id,
            prompt_name="outline_prompt",
            prompt_text=prompt_text,
            prompt_snapshot_path=str(snapshot.resolve()),
            workflow_stage=state.workflow_stage,
            model_hint=model_hint,
            instructions=instructions,
        )

    @router.post(
        "/projects/{project_id}/outline/import",
        response_model=OutlineImportResult,
    )
    def import_outline(
        project_id: str,
        request: OutlineImportRequest,
    ) -> OutlineImportResult:
        parsed = outline_service.import_outline(project_id, request.raw_text)
        state = workspace_manager.load_state(project_id)
        return OutlineImportResult(
            project_id=project_id,
            project_root=str(workspace_manager.get_project_root(project_id).resolve()),
            state_path=str(workspace_manager.get_state_path(project_id).resolve()),
            workflow_stage=state.workflow_stage,
            parse_result=parsed,
            state=state,
        )

    @router.put(
        "/projects/{project_id}/outline/confirmed",
        response_model=ProjectStateResponse,
    )
    def confirm_outline(
        project_id: str,
        request: OutlineConfirmRequest,
    ) -> ProjectStateResponse:
        outline_service.confirm_outline(project_id, request.outline_tree)
        state = workspace_manager.load_state(project_id)
        project_root = workspace_manager.get_project_root(project_id)
        state_path = workspace_manager.get_state_path(project_id)
        return ProjectStateResponse(
            project_id=project_id,
            project_root=str(project_root.resolve()),
            state_path=str(state_path.resolve()),
            workflow_stage=state.workflow_stage,
            state=state,
        )

    @router.get(
        "/projects/{project_id}/prompts/chunk-plan",
        response_model=PromptPreviewResponse,
    )
    def get_chunk_plan_prompt(project_id: str) -> PromptPreviewResponse:
        prompt_text, snapshot = prompt_factory.render_chunk_plan_prompt(project_id)
        state = workspace_manager.load_state(project_id)
        model_hint, instructions = _load_prompt_metadata("chunk_plan")
        return PromptPreviewResponse(
            project_id=project_id,
            prompt_name="chunk_plan_prompt",
            prompt_text=prompt_text,
            prompt_snapshot_path=str(snapshot.resolve()),
            workflow_stage=state.workflow_stage,
            model_hint=model_hint,
            instructions=instructions,
        )

    @router.post(
        "/projects/{project_id}/chunk-plan/import",
        response_model=ChunkPlanImportResult,
    )
    def import_chunk_plan(
        project_id: str,
        request: ChunkPlanImportRequest,
    ) -> ChunkPlanImportResult:
        parsed = chunk_plan_service.import_chunk_plan(project_id, request.raw_text)
        state = workspace_manager.load_state(project_id)
        return ChunkPlanImportResult(
            project_id=project_id,
            project_root=str(workspace_manager.get_project_root(project_id).resolve()),
            state_path=str(workspace_manager.get_state_path(project_id).resolve()),
            workflow_stage=state.workflow_stage,
            parse_result=parsed,
            state=state,
        )

    @router.put(
        "/projects/{project_id}/chunk-plan/confirmed",
        response_model=ProjectStateResponse,
    )
    def confirm_chunk_plan(
        project_id: str,
        request: ChunkPlanConfirmRequest,
    ) -> ProjectStateResponse:
        chunk_plan_service.confirm_chunk_plan(project_id, request.chunk_plan)
        state = workspace_manager.load_state(project_id)
        project_root = workspace_manager.get_project_root(project_id)
        state_path = workspace_manager.get_state_path(project_id)
        return ProjectStateResponse(
            project_id=project_id,
            project_root=str(project_root.resolve()),
            state_path=str(state_path.resolve()),
            workflow_stage=state.workflow_stage,
            state=state,
        )

    @router.get(
        "/projects/{project_id}/prompts/blocks/{block_index}/generate",
        response_model=PromptPreviewResponse,
    )
    def get_block_generation_prompt(
        project_id: str,
        block_index: int,
    ) -> PromptPreviewResponse:
        prompt_text, snapshot = prompt_factory.render_block_generation_prompt(
            project_id,
            block_index,
        )
        state = workspace_manager.load_state(project_id)
        model_hint, instructions = _load_prompt_metadata("block_generation")
        return PromptPreviewResponse(
            project_id=project_id,
            prompt_name=f"block_{block_index:02d}_generate_prompt",
            prompt_text=prompt_text,
            prompt_snapshot_path=str(snapshot.resolve()),
            workflow_stage=state.workflow_stage,
            model_hint=model_hint,
            instructions=instructions,
        )

    @router.get(
        "/projects/{project_id}/prompts/blocks/{block_index}/compress",
        response_model=PromptPreviewResponse,
    )
    def get_block_compress_prompt(
        project_id: str,
        block_index: int,
    ) -> PromptPreviewResponse:
        prompt_text, snapshot = prompt_factory.render_compress_prompt(project_id, block_index)
        state = workspace_manager.load_state(project_id)
        model_hint, instructions = _load_prompt_metadata("compression")
        return PromptPreviewResponse(
            project_id=project_id,
            prompt_name=f"block_{block_index:02d}_compress_prompt",
            prompt_text=prompt_text,
            prompt_snapshot_path=str(snapshot.resolve()),
            workflow_stage=state.workflow_stage,
            model_hint=model_hint,
            instructions=instructions,
        )

    @router.get(
        "/projects/{project_id}/prompts/abstract",
        response_model=PromptPreviewResponse,
    )
    def get_abstract_prompt(project_id: str) -> PromptPreviewResponse:
        prompt_text, snapshot = prompt_factory.render_abstract_prompt(project_id)
        state = workspace_manager.load_state(project_id)
        model_hint, instructions = _load_prompt_metadata("abstract")
        return PromptPreviewResponse(
            project_id=project_id,
            prompt_name="abstract_prompt",
            prompt_text=prompt_text,
            prompt_snapshot_path=str(snapshot.resolve()),
            workflow_stage=state.workflow_stage,
            model_hint=model_hint,
            instructions=instructions,
        )

    @router.post(
        "/projects/{project_id}/blocks/{block_index}/import",
        response_model=BlockImportResult,
    )
    def import_block_content(
        project_id: str,
        block_index: int,
        request: BlockImportRequest,
    ) -> BlockImportResult:
        parsed = generation_service.import_block_content(project_id, block_index, request.raw_text)
        state = workspace_manager.load_state(project_id)
        return BlockImportResult(
            project_id=project_id,
            block_index=block_index,
            workflow_stage=state.workflow_stage,
            parse_result=parsed,
            state=state,
        )

    @router.post(
        "/projects/{project_id}/blocks/{block_index}/compressed-context/import",
        response_model=BlockImportResult,
    )
    def import_compressed_context(
        project_id: str,
        block_index: int,
        request: CompressedContextImportRequest,
    ) -> BlockImportResult:
        parsed = generation_service.import_compressed_context(
            project_id,
            block_index,
            request.raw_text,
        )
        state = workspace_manager.load_state(project_id)
        return BlockImportResult(
            project_id=project_id,
            block_index=block_index,
            workflow_stage=state.workflow_stage,
            parse_result=parsed,
            state=state,
        )

    @router.post(
        "/projects/{project_id}/abstract/import",
        response_model=BlockImportResult,
    )
    def import_abstract(
        project_id: str,
        request: AbstractImportRequest,
    ) -> BlockImportResult:
        parsed = generation_service.import_abstract(project_id, request.raw_text)
        state = workspace_manager.load_state(project_id)
        return BlockImportResult(
            project_id=project_id,
            block_index=state.generation.total_blocks,
            workflow_stage=state.workflow_stage,
            parse_result=parsed,
            state=state,
        )

    @router.post(
        "/projects/{project_id}/references/{source_index}/skip",
        response_model=SkipReferenceResponse,
    )
    def skip_reference(
        project_id: str,
        source_index: int,
        request: SkipReferenceRequest,
    ) -> SkipReferenceResponse:
        item = reference_service.skip_reference(project_id, source_index, request.reason)
        state = workspace_manager.load_state(project_id)
        return SkipReferenceResponse(
            project_id=project_id,
            source_index=source_index,
            status="skipped",
            workflow_stage=state.workflow_stage,
            item=item,
        )

    @router.post(
        "/projects/{project_id}/references/{source_index}/pdf",
        response_model=ProcessedReferenceResponse,
    )
    def import_reference_pdf(
        project_id: str,
        source_index: int,
        request: ReferencePdfImportRequest,
    ) -> ProcessedReferenceResponse:
        item = reference_service.import_reference_pdf(project_id, source_index, request.pdf_path)
        state = workspace_manager.load_state(project_id)
        return ProcessedReferenceResponse(
            project_id=project_id,
            workflow_stage=state.workflow_stage,
            item=ProcessedReferencePayload.model_validate(item.model_dump(mode="json")),
        )

    @router.post(
        "/projects/{project_id}/references/pdfs/batch",
        response_model=BatchImportResult,
    )
    def batch_import_pdfs(
        project_id: str,
        request: BatchPdfImportRequest,
    ) -> BatchImportResult:
        processed_items, review_items = reference_service.batch_import_pdfs(
            project_id,
            request.pdf_paths,
        )
        state = workspace_manager.load_state(project_id)
        return BatchImportResult(
            project_id=project_id,
            project_root=str(workspace_manager.get_project_root(project_id).resolve()),
            state_path=str(workspace_manager.get_state_path(project_id).resolve()),
            workflow_stage=state.workflow_stage,
            processed_items=[
                ProcessedReferencePayload.model_validate(item.model_dump(mode="json"))
                for item in processed_items
            ],
            review_items=[BatchReviewItem(**item) for item in review_items],
            state=state,
        )

    @router.post(
        "/projects/{project_id}/references/bibtex/import",
        response_model=BibtexImportResult,
    )
    def import_bibtex(
        project_id: str,
        request: BibtexImportRequest,
    ) -> BibtexImportResult:
        entries = reference_service.import_bibtex_entries(project_id, request.raw_text)
        state = workspace_manager.load_state(project_id)
        return BibtexImportResult(
            project_id=project_id,
            project_root=str(workspace_manager.get_project_root(project_id).resolve()),
            state_path=str(workspace_manager.get_state_path(project_id).resolve()),
            workflow_stage=state.workflow_stage,
            imported_count=len(entries),
            state=state,
        )

    @router.post(
        "/projects/{project_id}/export/docx",
        response_model=ExportProjectResult,
    )
    def export_docx(
        project_id: str,
        request: ExportProjectRequest,
    ) -> ExportProjectResult:
        export_result = export_service.export_project(
            project_id,
            output_filename=request.output_filename,
        )
        state = workspace_manager.load_state(project_id)
        return ExportProjectResult(
            project_id=project_id,
            workflow_stage=state.workflow_stage,
            output_path=export_result.output_path,
            log_path=export_result.log_path,
            reference_count=export_result.reference_count,
            message=export_result.message,
            state=state,
            export_history=[
                {
                    "output_path": item.output_path,
                    "exported_at": item.exported_at,
                    "reference_count": item.reference_count,
                    "log_path": item.log_path,
                }
                for item in state.export.history
            ],
        )

    @router.post("/contracts/{contract_type}/parse", response_model=ContractParseResult)
    def parse_contract(
        contract_type: ContractType,
        request: ContractParseRequest,
    ) -> ContractParseResult:
        parsed = contract_parser.parse(
            contract_type,
            request.raw_text,
            project_id=request.project_id,
        )
        return ContractParseResult(
            contract_type=parsed.contract_type.value,
            raw_text=parsed.raw_text,
            normalized_json_text=parsed.normalized_json_text,
            parsed_object=parsed.parsed_object,
            errors=parsed.errors,
            warnings=parsed.warnings,
            raw_snapshot_path=parsed.raw_snapshot_path,
            normalized_snapshot_path=parsed.normalized_snapshot_path,
        )

    return router


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        # Get user-friendly Chinese error message
        user_message = exc.get_user_message()
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=exc.error_code,
                message=user_message,
                details=exc.details,
            ).model_dump(mode="json"),
        )
