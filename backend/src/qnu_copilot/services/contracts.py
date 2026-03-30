from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from pydantic import BaseModel, ValidationError

from qnu_copilot.domain.contracts import (
    BlockContentContract,
    ChunkPlanContract,
    CompressedContextContract,
    OutlineContract,
    ReferenceRecommendationContract,
)
from qnu_copilot.domain.enums import ContractType
from qnu_copilot.services.errors import ContractValidationError, InvalidInputError
from qnu_copilot.services.workspace import WorkspaceManager


CONTRACT_MODEL_MAP: dict[ContractType, type[BaseModel]] = {
    ContractType.REFERENCE_RECOMMENDATION: ReferenceRecommendationContract,
    ContractType.OUTLINE: OutlineContract,
    ContractType.CHUNK_PLAN: ChunkPlanContract,
    ContractType.BLOCK_CONTENT: BlockContentContract,
    ContractType.COMPRESSED_CONTEXT: CompressedContextContract,
}


class ParsedContract(BaseModel):
    contract_type: ContractType
    raw_text: str
    normalized_json_text: str
    parsed_object: dict[str, Any] | list[Any]
    errors: list[str]
    warnings: list[str]
    raw_snapshot_path: str | None = None
    normalized_snapshot_path: str | None = None


class ContractParserService:
    def __init__(self, workspace_manager: WorkspaceManager) -> None:
        self.workspace_manager = workspace_manager

    def parse(
        self,
        contract_type: ContractType,
        raw_text: str,
        *,
        project_id: str | None = None,
    ) -> ParsedContract:
        if not raw_text.strip():
            raise InvalidInputError("raw_text must not be empty")

        warnings: list[str] = []
        cleaned_text = raw_text.lstrip("\ufeff")
        if cleaned_text != raw_text:
            warnings.append("removed_utf8_bom")

        quote_normalized = self._normalize_quotes(cleaned_text)
        if quote_normalized != cleaned_text:
            warnings.append("normalized_fullwidth_quotes")

        no_code_fences = self._remove_code_fences(quote_normalized)
        if no_code_fences != quote_normalized:
            warnings.append("removed_markdown_code_fences")

        candidate = self._extract_json_candidate(no_code_fences)
        normalized_json_text, parsed_object, decode_warnings = self._decode_candidate(candidate)
        warnings.extend(decode_warnings)

        model_cls = CONTRACT_MODEL_MAP[contract_type]
        try:
            validated = model_cls.model_validate(parsed_object)
        except ValidationError as exc:
            raise ContractValidationError(
                "contract validation failed",
                details={"errors": exc.errors()},
            ) from exc

        raw_snapshot_path: str | None = None
        normalized_snapshot_path: str | None = None
        if project_id:
            raw_snapshot, normalized_snapshot = self.workspace_manager.write_ai_snapshot(
                project_id,
                contract_name=contract_type.value,
                raw_text=raw_text,
                normalized_json_text=normalized_json_text,
            )
            raw_snapshot_path = str(raw_snapshot.resolve())
            normalized_snapshot_path = (
                str(normalized_snapshot.resolve()) if normalized_snapshot else None
            )

        return ParsedContract(
            contract_type=contract_type,
            raw_text=raw_text,
            normalized_json_text=normalized_json_text,
            parsed_object=validated.model_dump(mode="json"),
            errors=[],
            warnings=warnings,
            raw_snapshot_path=raw_snapshot_path,
            normalized_snapshot_path=normalized_snapshot_path,
        )

    def _normalize_quotes(self, text: str) -> str:
        return (
            text.replace("“", '"')
            .replace("”", '"')
            .replace("‘", "'")
            .replace("’", "'")
        )

    def _remove_code_fences(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 2:
                return "\n".join(lines[1:-1]).strip()
        return text

    def _extract_json_candidate(self, text: str) -> str:
        object_index = text.find("{")
        array_index = text.find("[")
        candidates = [index for index in [object_index, array_index] if index != -1]
        if not candidates:
            raise ContractValidationError(
                "no JSON object or array found in raw_text",
                details={"errors": ["missing_json_root"]},
            )
        start_index = min(candidates)
        return text[start_index:].strip()

    def _decode_candidate(
        self,
        candidate: str,
    ) -> tuple[str, dict[str, Any] | list[Any], list[str]]:
        warnings: list[str] = []
        decoder = json.JSONDecoder()
        try:
            parsed_object, end_index = decoder.raw_decode(candidate)
            normalized = candidate[:end_index]
            if candidate[end_index:].strip():
                warnings.append("discarded_trailing_text")
            return normalized, parsed_object, warnings
        except JSONDecodeError:
            fixed_candidate = self._attempt_single_closer_fix(candidate)
            if not fixed_candidate:
                raise ContractValidationError(
                    "failed to decode JSON payload",
                    details={"errors": ["json_decode_failed"]},
                )
            try:
                parsed_object, end_index = decoder.raw_decode(fixed_candidate)
            except JSONDecodeError as exc:
                raise ContractValidationError(
                    "failed to decode JSON payload after repair attempt",
                    details={"errors": [str(exc)]},
                ) from exc
            warnings.append("appended_single_missing_closer")
            normalized = fixed_candidate[:end_index]
            if fixed_candidate[end_index:].strip():
                warnings.append("discarded_trailing_text")
            return normalized, parsed_object, warnings

    def _attempt_single_closer_fix(self, candidate: str) -> str | None:
        stripped = candidate.rstrip()
        if not stripped:
            return None
        root = stripped[0]
        if root == "{" and stripped.count("{") == stripped.count("}") + 1:
            return f"{stripped}}}"
        if root == "[" and stripped.count("[") == stripped.count("]") + 1:
            return f"{stripped}]"
        return None
