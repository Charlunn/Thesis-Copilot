from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from qnu_copilot.domain.contracts import ConfirmedOutlineContract, OutlineContract
from qnu_copilot.domain.enums import ContractType, GenericStatus, WorkflowStage
from qnu_copilot.services.contracts import ContractParserService, ParsedContract
from qnu_copilot.services.errors import ConflictError, ContractValidationError
from qnu_copilot.services.workspace import WorkspaceManager


class OutlineService:
    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        contract_parser: ContractParserService,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.contract_parser = contract_parser

    def import_outline(self, project_id: str, raw_text: str) -> ParsedContract:
        state = self.workspace_manager.load_state(project_id)
        if len(state.references.processed_items) < state.references.minimum_required:
            raise ConflictError(
                "outline import requires the minimum number of processed PDFs"
            )

        parsed = self.contract_parser.parse(
            ContractType.OUTLINE,
            raw_text,
            project_id=project_id,
        )
        contract = OutlineContract.model_validate(parsed.parsed_object)
        confirmed_tree = self._build_confirmed_tree(contract.model_dump(mode="json"))

        state.outline.raw_ai_text = raw_text
        state.outline.normalized_json = contract.model_dump(mode="json")
        state.outline.confirmed_tree = confirmed_tree
        state.outline.status = GenericStatus.READY
        state.workflow_stage = WorkflowStage.OUTLINE_EDITING
        self.workspace_manager.save_state(project_id, state)
        return parsed

    def confirm_outline(
        self,
        project_id: str,
        outline_tree: dict[str, Any],
    ) -> dict[str, Any]:
        state = self.workspace_manager.load_state(project_id)
        if not state.outline.normalized_json:
            raise ConflictError("outline must be imported before it can be confirmed")

        try:
            contract = ConfirmedOutlineContract.model_validate(outline_tree)
        except ValidationError as exc:
            raise ContractValidationError(
                "confirmed outline validation failed",
                details={"errors": exc.errors()},
            ) from exc

        normalized_tree = contract.model_dump(mode="json")
        state.outline.confirmed_tree = normalized_tree
        state.outline.status = GenericStatus.COMPLETED
        state.workflow_stage = WorkflowStage.CHUNK_PLANNING
        self.workspace_manager.save_state(project_id, state)
        return normalized_tree

    def _build_confirmed_tree(self, outline_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": outline_payload["title"],
            "outline": [self._enrich_node(node) for node in outline_payload["outline"]],
        }

    def _enrich_node(self, node: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": node["id"],
            "level": node["level"],
            "title": node["title"],
            "enabled": True,
            "must_be_separate_block": False,
            "children": [self._enrich_node(child) for child in node.get("children", [])],
        }
