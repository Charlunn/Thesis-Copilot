from __future__ import annotations

from qnu_copilot.domain.contracts import AbstractContract, BlockContentContract, CompressedContextContract
from qnu_copilot.domain.enums import ContractType, GenericStatus, WorkflowStage
from qnu_copilot.services.contracts import ContractParserService, ParsedContract
from qnu_copilot.services.errors import ConflictError
from qnu_copilot.services.workspace import WorkspaceManager


class GenerationService:
    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        contract_parser: ContractParserService,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.contract_parser = contract_parser

    def import_block_content(
        self,
        project_id: str,
        block_index: int,
        raw_text: str,
    ) -> ParsedContract:
        state = self.workspace_manager.load_state(project_id)
        if not state.chunk_plan.confirmed_plan:
            raise ConflictError("confirmed chunk plan is required before importing block content")
        if block_index != state.generation.current_block_index:
            raise ConflictError("block content must be imported in sequence")

        block_state = self._get_generation_block(state.generation.blocks, block_index)
        if block_state.normalized_json is not None:
            raise ConflictError("block content was already imported")
        if block_index == state.generation.total_blocks and state.generation.abstract_json is not None:
            raise ConflictError("abstract already exists; body blocks cannot be re-imported")

        parsed = self.contract_parser.parse(
            ContractType.BLOCK_CONTENT,
            raw_text,
            project_id=project_id,
        )
        contract = BlockContentContract.model_validate(parsed.parsed_object)
        if contract.block_index != block_index:
            raise ConflictError("block_index in payload does not match the requested route")

        block_state.raw_ai_text = raw_text
        block_state.normalized_json = contract.model_dump(mode="json")
        block_state.status = GenericStatus.COMPLETED
        state.generation.status = GenericStatus.IN_PROGRESS

        if block_index == state.generation.total_blocks:
            state.generation.current_block_index = block_index
            state.generation.status = GenericStatus.IN_PROGRESS
            state.generation.abstract_status = GenericStatus.READY
            state.workflow_stage = WorkflowStage.ABSTRACT_GENERATION
        self.workspace_manager.save_state(project_id, state)
        return parsed

    def import_compressed_context(
        self,
        project_id: str,
        block_index: int,
        raw_text: str,
    ) -> ParsedContract:
        state = self.workspace_manager.load_state(project_id)
        if not state.chunk_plan.confirmed_plan:
            raise ConflictError("confirmed chunk plan is required before importing compressed context")
        if block_index != state.generation.current_block_index:
            raise ConflictError("compressed context must be imported for the active block")
        if block_index >= state.generation.total_blocks:
            raise ConflictError("the final block does not require compressed context")

        block_state = self._get_generation_block(state.generation.blocks, block_index)
        if block_state.normalized_json is None:
            raise ConflictError("block content must be imported before compressed context")
        if block_state.compressed_context_json is not None:
            raise ConflictError("compressed context for this block was already imported")

        parsed = self.contract_parser.parse(
            ContractType.COMPRESSED_CONTEXT,
            raw_text,
            project_id=project_id,
        )
        contract = CompressedContextContract.model_validate(parsed.parsed_object)
        expected_blocks = list(range(1, block_index + 1))
        if contract.covered_blocks != expected_blocks:
            raise ConflictError("covered_blocks must exactly match all completed blocks so far")

        block_state.compressed_context_raw_ai_text = raw_text
        block_state.compressed_context_json = contract.model_dump(mode="json")
        state.generation.latest_compressed_context = contract.model_dump(mode="json")
        state.generation.current_block_index = block_index + 1
        state.workflow_stage = WorkflowStage.BLOCK_GENERATION
        self.workspace_manager.save_state(project_id, state)
        return parsed

    def import_abstract(self, project_id: str, raw_text: str) -> ParsedContract:
        state = self.workspace_manager.load_state(project_id)
        if not state.chunk_plan.confirmed_plan:
            raise ConflictError("confirmed chunk plan is required before importing abstract")
        if any(block.normalized_json is None for block in state.generation.blocks):
            raise ConflictError("all body blocks must be imported before abstract")
        if state.generation.abstract_json is not None:
            raise ConflictError("abstract was already imported")

        parsed = self.contract_parser.parse(
            ContractType.ABSTRACT,
            raw_text,
            project_id=project_id,
        )
        contract = AbstractContract.model_validate(parsed.parsed_object)
        state.generation.abstract_raw_ai_text = raw_text
        state.generation.abstract_json = contract.model_dump(mode="json")
        state.generation.abstract_status = GenericStatus.COMPLETED
        state.generation.status = GenericStatus.COMPLETED
        state.workflow_stage = WorkflowStage.EXPORT
        self.workspace_manager.save_state(project_id, state)
        return parsed

    def _get_generation_block(self, blocks, block_index: int):
        for block in blocks:
            if block.block_index == block_index:
                return block
        raise ConflictError(f"generation block does not exist: {block_index}")
