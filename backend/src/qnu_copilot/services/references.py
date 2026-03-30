from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from qnu_copilot.domain.contracts import ReferenceRecommendationContract
from qnu_copilot.domain.enums import (
    ContractType,
    ReferenceSourceMode,
    ReferenceStatus,
    SkipReason,
    WorkflowStage,
)
from qnu_copilot.domain.models import BibtexEntry, ProcessedReferenceItem, RecommendedReferenceItem
from qnu_copilot.services.contracts import ContractParserService, ParsedContract
from qnu_copilot.services.errors import ConflictError, InvalidInputError, NotFoundError
from qnu_copilot.services.filesystem import (
    build_processed_filename,
    build_raw_copy_name,
    compute_sha256,
    ensure_existing_pdf,
    normalize_lookup_key,
    sanitize_title,
)
from qnu_copilot.services.workspace import WorkspaceManager


BIBTEX_KEY_RE = re.compile(r"@\w+\s*{\s*([^,\s]+)")
BIBTEX_ENTRY_RE = re.compile(r"@\w+\s*{.*?(?=@\w+\s*{|$)", re.DOTALL)


class ReferenceService:
    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        contract_parser: ContractParserService,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.contract_parser = contract_parser

    def import_recommendations(self, project_id: str, raw_text: str) -> ParsedContract:
        state = self.workspace_manager.load_state(project_id)
        if state.references.recommended_items or state.references.processed_items:
            raise ConflictError("reference recommendations were already initialized")

        parsed = self.contract_parser.parse(
            ContractType.REFERENCE_RECOMMENDATION,
            raw_text,
            project_id=project_id,
        )
        contract = ReferenceRecommendationContract.model_validate(parsed.parsed_object)
        state.references.source_mode = ReferenceSourceMode.RECOMMENDED
        state.references.recommended_items = [
            RecommendedReferenceItem(
                source_index=index,
                title=paper.title,
                language=paper.language,
                download_url=paper.download_url,
                venue=paper.venue,
                year=paper.year,
                impact_note=paper.impact_note,
                bibtex_key=self._extract_bibtex_key(paper.bibtex),
            )
            for index, paper in enumerate(contract.papers, start=1)
        ]
        state.references.bibtex_entries = [
            BibtexEntry(
                key=self._extract_bibtex_key(paper.bibtex),
                raw_text=paper.bibtex,
                title=paper.title,
            )
            for paper in contract.papers
        ]
        state.workflow_stage = WorkflowStage.PDF_PROCESSING
        self.workspace_manager.save_state(project_id, state)
        return parsed

    def import_bibtex_entries(self, project_id: str, raw_text: str) -> list[BibtexEntry]:
        state = self.workspace_manager.load_state(project_id)
        entries = self._parse_bibtex_entries(raw_text)
        if not entries:
            raise InvalidInputError("no BibTeX entries were found in the pasted text")

        state.references.bibtex_entries = entries
        entry_by_title = {
            normalize_lookup_key(entry.title): entry
            for entry in entries
            if entry.title
        }
        entry_by_key = {entry.key: entry for entry in entries if entry.key}

        for item in state.references.recommended_items:
            matched = entry_by_key.get(item.bibtex_key) or entry_by_title.get(
                normalize_lookup_key(item.title)
            )
            if matched:
                item.bibtex_key = matched.key

        for item in state.references.processed_items:
            matched = entry_by_key.get(item.bibtex_key) or entry_by_title.get(
                normalize_lookup_key(item.title)
            )
            if matched:
                item.bibtex_key = matched.key

        self.workspace_manager.save_state(project_id, state)
        return entries

    def skip_reference(
        self,
        project_id: str,
        source_index: int,
        reason: SkipReason | str,
    ) -> RecommendedReferenceItem:
        state = self.workspace_manager.load_state(project_id)
        if not state.references.recommended_items:
            raise ConflictError("skip is only available after recommendation import")
        item = self._get_recommended_item(state.references.recommended_items, source_index)
        if item.status == ReferenceStatus.IMPORTED:
            raise ConflictError("cannot skip a reference that is already imported")
        if item.status in {
            ReferenceStatus.SKIPPED_UNAVAILABLE,
            ReferenceStatus.SKIPPED_USER_CHOICE,
        }:
            return item
        item.status = (
            ReferenceStatus.SKIPPED_UNAVAILABLE
            if SkipReason(reason) == SkipReason.UNAVAILABLE
            else ReferenceStatus.SKIPPED_USER_CHOICE
        )
        self._refresh_workflow_stage(state)
        self.workspace_manager.save_state(project_id, state)
        return item

    def import_reference_pdf(
        self,
        project_id: str,
        source_index: int,
        pdf_path: str,
    ) -> ProcessedReferenceItem:
        state = self.workspace_manager.load_state(project_id)
        if not state.references.recommended_items:
            raise ConflictError("single-reference import requires recommended_items")
        item = self._get_recommended_item(state.references.recommended_items, source_index)
        if item.status == ReferenceStatus.IMPORTED:
            return self._get_processed_item_by_source_index(
                state.references.processed_items,
                source_index,
            )
        if item.status in {
            ReferenceStatus.SKIPPED_UNAVAILABLE,
            ReferenceStatus.SKIPPED_USER_CHOICE,
        }:
            raise ConflictError("cannot import a reference that was already skipped")

        processed_item = self._import_pdf_into_state(
            project_id,
            state,
            pdf_path=pdf_path,
            title=item.title,
            language=item.language,
            source_index=item.source_index,
            bibtex_key=item.bibtex_key,
        )
        item.status = ReferenceStatus.IMPORTED
        self._refresh_workflow_stage(state)
        self.workspace_manager.save_state(project_id, state)
        return processed_item

    def batch_import_pdfs(
        self,
        project_id: str,
        pdf_paths: list[str],
    ) -> tuple[list[ProcessedReferenceItem], list[dict[str, str]]]:
        if not pdf_paths:
            raise InvalidInputError("pdf_paths must not be empty")

        state = self.workspace_manager.load_state(project_id)
        processed_items: list[ProcessedReferenceItem] = []
        review_items: list[dict[str, str]] = []

        if state.references.recommended_items:
            matched_jobs = []
            lookup: dict[str, list[RecommendedReferenceItem]] = {}
            for item in state.references.recommended_items:
                lookup.setdefault(normalize_lookup_key(item.title), []).append(item)

            for raw_path in pdf_paths:
                path = ensure_existing_pdf(raw_path)
                key = normalize_lookup_key(path.stem)
                candidates = lookup.get(key, [])
                pending = next(
                    (
                        candidate
                        for candidate in candidates
                        if candidate.status == ReferenceStatus.PENDING
                    ),
                    None,
                )
                if not pending:
                    review_items.append(
                        {
                            "file_path": str(path.resolve()),
                            "reason": "no pending recommended reference matched this filename",
                        }
                    )
                    continue
                matched_jobs.append((pending.source_index, str(path)))

            for source_index, raw_path in sorted(matched_jobs, key=lambda item: item[0]):
                processed_items.append(
                    self.import_reference_pdf(project_id, source_index, raw_path)
                )
            return processed_items, review_items

        if state.project.need_reference_recommendation:
            raise ConflictError(
                "recommendation import must happen before manual PDF batch import"
            )

        state.references.source_mode = ReferenceSourceMode.MANUAL
        state.workflow_stage = WorkflowStage.PDF_PROCESSING
        for raw_path in sorted(pdf_paths, key=lambda value: Path(value).name.lower()):
            path = ensure_existing_pdf(raw_path)
            processed_items.append(
                self._import_pdf_into_state(
                    project_id,
                    state,
                    pdf_path=str(path),
                    title=path.stem,
                    language=None,
                    source_index=None,
                    bibtex_key=None,
                )
            )
        self._refresh_workflow_stage(state)
        self.workspace_manager.save_state(project_id, state)
        return processed_items, review_items

    def _import_pdf_into_state(
        self,
        project_id: str,
        state: Any,
        *,
        pdf_path: str,
        title: str,
        language: str | None,
        source_index: int | None,
        bibtex_key: str | None,
    ) -> ProcessedReferenceItem:
        source_pdf = ensure_existing_pdf(pdf_path)
        sha256_hex = compute_sha256(source_pdf)
        existing_by_hash = next(
            (item for item in state.references.processed_items if item.sha256 == sha256_hex),
            None,
        )
        if existing_by_hash:
            if existing_by_hash.source_index == source_index:
                return existing_by_hash
            raise ConflictError("the same PDF file is already attached to another reference")

        project_root = self.workspace_manager.get_project_root(project_id)
        raw_dir = project_root / "raw_pdfs"
        processed_dir = project_root / "processed_pdfs"

        raw_copy_path = raw_dir / build_raw_copy_name(source_pdf.name, sha256_hex)
        if not raw_copy_path.exists():
            shutil.copy2(source_pdf, raw_copy_path)

        effective_index = state.references.next_sequence
        title_hash_suffix = None
        conflicting_title = next(
            (
                item
                for item in state.references.processed_items
                if item.normalized_title == sanitize_title(title) and item.sha256 != sha256_hex
            ),
            None,
        )
        if conflicting_title:
            title_hash_suffix = sha256_hex[:8]

        processed_filename = build_processed_filename(
            effective_index,
            title,
            hash_suffix=title_hash_suffix,
        )
        processed_copy_path = processed_dir / processed_filename
        if processed_copy_path.exists():
            processed_copy_path = processed_dir / build_processed_filename(
                effective_index,
                title,
                hash_suffix=sha256_hex[:8],
            )
        shutil.copy2(source_pdf, processed_copy_path)

        processed_item = ProcessedReferenceItem(
            effective_index=effective_index,
            source_index=source_index,
            title=title,
            normalized_title=sanitize_title(title),
            language=language,
            raw_pdf_path=str(raw_copy_path.resolve()),
            processed_pdf_path=str(processed_copy_path.resolve()),
            file_size=source_pdf.stat().st_size,
            sha256=sha256_hex,
            bibtex_key=bibtex_key,
        )
        state.references.processed_items.append(processed_item)
        state.references.next_sequence += 1
        return processed_item

    def _refresh_workflow_stage(self, state: Any) -> None:
        if len(state.references.processed_items) >= state.references.minimum_required:
            state.workflow_stage = WorkflowStage.OUTLINE_GENERATION
        elif (
            state.references.recommended_items
            or state.references.source_mode == ReferenceSourceMode.MANUAL
        ):
            state.workflow_stage = WorkflowStage.PDF_PROCESSING
        else:
            state.workflow_stage = WorkflowStage.REFERENCES

    def _extract_bibtex_key(self, bibtex_text: str) -> str | None:
        match = BIBTEX_KEY_RE.search(bibtex_text)
        return match.group(1) if match else None

    def _parse_bibtex_entries(self, raw_text: str) -> list[BibtexEntry]:
        normalized = raw_text.strip()
        if not normalized:
            raise InvalidInputError("BibTeX text must not be empty")

        entries = [chunk.strip() for chunk in BIBTEX_ENTRY_RE.findall(normalized) if chunk.strip()]
        if not entries and normalized.startswith("@"):
            entries = [normalized]

        parsed_entries: list[BibtexEntry] = []
        for entry_text in entries:
            key = self._extract_bibtex_key(entry_text)
            parsed_entries.append(
                BibtexEntry(
                    key=key,
                    raw_text=entry_text,
                    title=self._extract_bibtex_field(entry_text, "title"),
                )
            )
        return parsed_entries

    def _extract_bibtex_field(self, bibtex_text: str, field_name: str) -> str | None:
        field_match = re.search(
            rf"{field_name}\s*=\s*([{{\"])",
            bibtex_text,
            flags=re.IGNORECASE,
        )
        if not field_match:
            return None

        opening = field_match.group(1)
        cursor = field_match.end()

        if opening == '"':
            collected: list[str] = []
            escaped = False
            while cursor < len(bibtex_text):
                current = bibtex_text[cursor]
                cursor += 1
                if escaped:
                    collected.append(current)
                    escaped = False
                    continue
                if current == "\\":
                    escaped = True
                    continue
                if current == '"':
                    break
                collected.append(current)
            value = "".join(collected).strip()
            return value or None

        depth = 1
        collected = []
        while cursor < len(bibtex_text) and depth > 0:
            current = bibtex_text[cursor]
            cursor += 1
            if current == "{":
                depth += 1
                collected.append(current)
                continue
            if current == "}":
                depth -= 1
                if depth == 0:
                    break
                collected.append(current)
                continue
            collected.append(current)

        value = "".join(collected).strip()
        return value or None

    def _get_recommended_item(
        self,
        items: list[RecommendedReferenceItem],
        source_index: int,
    ) -> RecommendedReferenceItem:
        for item in items:
            if item.source_index == source_index:
                return item
        raise NotFoundError(f"reference source_index does not exist: {source_index}")

    def _get_processed_item_by_source_index(
        self,
        items: list[ProcessedReferenceItem],
        source_index: int,
    ) -> ProcessedReferenceItem:
        for item in items:
            if item.source_index == source_index:
                return item
        raise NotFoundError(f"processed reference not found for source_index: {source_index}")
