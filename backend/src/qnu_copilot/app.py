from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qnu_copilot.api.routes import create_router, install_error_handlers
from qnu_copilot.api.config_routes import create_config_router
from qnu_copilot.api.aigc_routes import create_aigc_router
from qnu_copilot.services.chunk_plan import ChunkPlanService
from qnu_copilot.services.contracts import ContractParserService
from qnu_copilot.services.export import LocalDocumentExportService, ProjectExportService
from qnu_copilot.services.generation import GenerationService
from qnu_copilot.services.outline import OutlineService
from qnu_copilot.services.prompts import PromptFactoryService
from qnu_copilot.services.references import ReferenceService
from qnu_copilot.services.workspace import WorkspaceManager


def create_app(data_root: str | Path | None = None) -> FastAPI:
    resolved_root = Path(data_root or ".qnu_copilot_data").expanduser().resolve()
    workspace_manager = WorkspaceManager(resolved_root)
    contract_parser = ContractParserService(workspace_manager)
    reference_service = ReferenceService(workspace_manager, contract_parser)
    outline_service = OutlineService(workspace_manager, contract_parser)
    chunk_plan_service = ChunkPlanService(workspace_manager, contract_parser)
    generation_service = GenerationService(workspace_manager, contract_parser)
    prompt_factory = PromptFactoryService(workspace_manager)
    export_service = ProjectExportService(
        workspace_manager,
        LocalDocumentExportService(),
    )

    app = FastAPI(title="QNU Thesis Copilot Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.data_root = resolved_root
    app.state.workspace_manager = workspace_manager
    app.state.contract_parser = contract_parser
    app.state.reference_service = reference_service
    app.state.outline_service = outline_service
    app.state.chunk_plan_service = chunk_plan_service
    app.state.generation_service = generation_service
    app.state.prompt_factory = prompt_factory
    app.state.export_service = export_service
    
    # Include config router for API settings
    app.include_router(create_config_router(resolved_root))
    
    # Include AIGC checking router
    app.include_router(create_aigc_router())
    
    # Include main project router
    app.include_router(
        create_router(
            workspace_manager,
            reference_service,
            contract_parser,
            outline_service,
            chunk_plan_service,
            generation_service,
            prompt_factory,
            export_service,
        )
    )
    install_error_handlers(app)
    return app
