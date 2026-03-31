from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from qnu_copilot.domain.contracts import ChunkPlanContract
from qnu_copilot.domain.enums import ContractType, GenericStatus, WorkflowStage
from qnu_copilot.domain.models import GeneratedBlockState
from qnu_copilot.services.contracts import ContractParserService, ParsedContract
from qnu_copilot.services.errors import ConflictError, ContractValidationError
from qnu_copilot.services.workspace import WorkspaceManager


class ChunkPlanService:
    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        contract_parser: ContractParserService,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.contract_parser = contract_parser

    def import_chunk_plan(self, project_id: str, raw_text: str) -> ParsedContract:
        state = self.workspace_manager.load_state(project_id)
        if not state.outline.confirmed_tree:
            raise ConflictError("chunk plan import requires a confirmed outline")

        parsed = self.contract_parser.parse(
            ContractType.CHUNK_PLAN,
            raw_text,
            project_id=project_id,
        )
        contract = ChunkPlanContract.model_validate(parsed.parsed_object)
        self._validate_chunk_plan_against_outline(contract, state.outline.confirmed_tree)

        state.chunk_plan.raw_ai_text = raw_text
        state.chunk_plan.normalized_json = contract.model_dump(mode="json")
        state.chunk_plan.status = GenericStatus.READY
        state.workflow_stage = WorkflowStage.CHUNK_PLANNING
        self.workspace_manager.save_state(project_id, state)
        return parsed

    def confirm_chunk_plan(
        self,
        project_id: str,
        chunk_plan: dict[str, Any],
    ) -> dict[str, Any]:
        state = self.workspace_manager.load_state(project_id)
        if not state.outline.confirmed_tree:
            raise ConflictError("confirmed outline is required before confirming chunk plan")
        if not state.chunk_plan.normalized_json:
            raise ConflictError("chunk plan must be imported before it can be confirmed")

        try:
            contract = ChunkPlanContract.model_validate(chunk_plan)
        except ValidationError as exc:
            raise ContractValidationError(
                "confirmed chunk plan validation failed",
                details={"errors": exc.errors()},
            ) from exc

        self._validate_chunk_plan_against_outline(contract, state.outline.confirmed_tree)

        if state.project.minimum_total_words:
            total_words = sum(block.minimum_words for block in contract.blocks)
            if total_words < state.project.minimum_total_words:
                raise ContractValidationError(
                    "confirmed chunk plan does not satisfy the minimum total words",
                    details={
                        "errors": [
                            {
                                "type": "minimum_total_words",
                                "message": "sum of block minimum_words is too small",
                                "required": state.project.minimum_total_words,
                                "actual": total_words,
                            }
                        ]
                    },
                )

        normalized_plan = contract.model_dump(mode="json")
        state.chunk_plan.confirmed_plan = normalized_plan
        state.chunk_plan.status = GenericStatus.COMPLETED
        state.workflow_stage = WorkflowStage.BLOCK_GENERATION
        state.generation.total_blocks = contract.total_blocks
        state.generation.current_block_index = 1 if contract.total_blocks else 0
        state.generation.blocks = [
            GeneratedBlockState(
                block_index=block.block_index,
                block_title=block.title,
            )
            for block in contract.blocks
        ]
        state.generation.latest_compressed_context = None
        state.generation.abstract_raw_ai_text = ""
        state.generation.abstract_json = None
        state.generation.abstract_status = GenericStatus.PENDING
        state.generation.status = (
            GenericStatus.READY if contract.total_blocks else GenericStatus.PENDING
        )
        self.workspace_manager.save_state(project_id, state)
        return normalized_plan

    def _validate_chunk_plan_against_outline(
        self,
        contract: ChunkPlanContract,
        confirmed_outline: dict[str, Any],
    ) -> None:
        enabled_node_ids = set(self._collect_enabled_outline_node_ids(confirmed_outline["outline"]))
        covered_node_ids = {
            node_id
            for block in contract.blocks
            for node_id in block.outline_node_ids
        }
        missing_node_ids = sorted(enabled_node_ids - covered_node_ids)
        if missing_node_ids:
            raise ContractValidationError(
                "chunk plan does not cover all enabled outline nodes",
                details={"errors": [{"missing_outline_node_ids": missing_node_ids}]},
            )

    def _collect_enabled_outline_node_ids(
        self,
        nodes: list[dict[str, Any]],
    ) -> list[str]:
        collected: list[str] = []
        for node in nodes:
            if node.get("enabled", True):
                collected.append(node["id"])
            collected.extend(self._collect_enabled_outline_node_ids(node.get("children", [])))
        return collected
