from __future__ import annotations

import json
from pathlib import Path

import pytest

from qnu_copilot.domain.models import ProjectInfo
from qnu_copilot.services.errors import InvalidInputError
from qnu_copilot.services.filesystem import sanitize_title
from qnu_copilot.services.references import ReferenceService
from qnu_copilot.services.workspace import WorkspaceManager


def build_recommendation_payload() -> str:
    papers = []
    for index in range(1, 16):
        papers.append(
            {
                "title": f"中文论文{index}",
                "language": "zh",
                "year": 2024,
                "venue": "中文期刊",
                "download_url": f"https://example.com/zh/{index}.pdf",
                "impact_note": "important",
                "bibtex": f"@article{{zh{index}, title={{中文论文{index}}}}}",
            }
        )
    for index in range(1, 16):
        papers.append(
            {
                "title": f"English Paper {index}",
                "language": "en",
                "year": 2024,
                "venue": "Conference",
                "download_url": f"https://example.com/en/{index}.pdf",
                "impact_note": "important",
                "bibtex": f"@article{{en{index}, title={{English Paper {index}}}}}",
            }
        )
    return json.dumps({"topic": "iot", "papers": papers}, ensure_ascii=False)


def write_pdf(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def create_project(workspace_manager: WorkspaceManager):
    state, _ = workspace_manager.create_project(
        ProjectInfo(
            title="Water Quality",
            core_idea="Create a local-first thesis workflow.",
            need_reference_recommendation=True,
        ),
        template_id="qnu-undergraduate-v1",
        minimum_required_references=2,
    )
    return state


def test_sanitize_title_handles_invalid_chars_and_whitespace() -> None:
    assert sanitize_title('  bad<>:"/\\\\|?* title   . ') == "bad title"


def test_skip_then_import_produces_contiguous_sequence(
    workspace_manager: WorkspaceManager,
    reference_service: ReferenceService,
    tmp_path: Path,
) -> None:
    state = create_project(workspace_manager)
    reference_service.import_recommendations(state.project_id, build_recommendation_payload())

    reference_service.skip_reference(state.project_id, 1, reason="unavailable")
    pdf_2 = write_pdf(tmp_path / "中文论文2.pdf", b"pdf-two")
    pdf_3 = write_pdf(tmp_path / "English Paper 1.pdf", b"pdf-three")

    item_2 = reference_service.import_reference_pdf(state.project_id, 2, str(pdf_2))
    item_3 = reference_service.import_reference_pdf(state.project_id, 16, str(pdf_3))

    assert item_2.effective_index == 1
    assert item_3.effective_index == 2
    assert Path(item_2.processed_pdf_path).name.startswith("01_")
    assert Path(item_3.processed_pdf_path).name.startswith("02_")


def test_batch_import_manual_mode_sorts_and_persists(
    workspace_manager: WorkspaceManager,
    reference_service: ReferenceService,
    tmp_path: Path,
) -> None:
    state, _ = workspace_manager.create_project(
        ProjectInfo(
            title="Manual Mode",
            core_idea="Import already downloaded PDFs.",
            need_reference_recommendation=False,
        ),
        template_id="qnu-undergraduate-v1",
        minimum_required_references=2,
    )
    pdf_b = write_pdf(tmp_path / "Beta.pdf", b"beta")
    pdf_a = write_pdf(tmp_path / "Alpha.pdf", b"alpha")

    processed_items, review_items = reference_service.batch_import_pdfs(
        state.project_id,
        [str(pdf_b), str(pdf_a)],
    )

    assert review_items == []
    assert [Path(item.processed_pdf_path).name for item in processed_items] == [
        "01_Alpha.pdf",
        "02_Beta.pdf",
    ]
    reloaded = workspace_manager.load_state(state.project_id)
    assert reloaded.workflow_stage.value == "outline_generation"


def test_batch_import_with_recommendations_returns_review_items(
    workspace_manager: WorkspaceManager,
    reference_service: ReferenceService,
    tmp_path: Path,
) -> None:
    state = create_project(workspace_manager)
    reference_service.import_recommendations(state.project_id, build_recommendation_payload())
    matching = write_pdf(tmp_path / "中文论文1.pdf", b"pdf-one")
    unmatched = write_pdf(tmp_path / "unknown.pdf", b"pdf-two")

    processed_items, review_items = reference_service.batch_import_pdfs(
        state.project_id,
        [str(unmatched), str(matching)],
    )

    assert len(processed_items) == 1
    assert len(review_items) == 1
    assert review_items[0]["file_path"].endswith("unknown.pdf")


def test_import_rejects_non_pdf(
    workspace_manager: WorkspaceManager,
    reference_service: ReferenceService,
    tmp_path: Path,
) -> None:
    state = create_project(workspace_manager)
    reference_service.import_recommendations(state.project_id, build_recommendation_payload())
    non_pdf = tmp_path / "bad.txt"
    non_pdf.write_text("not pdf", encoding="utf-8")

    with pytest.raises(InvalidInputError):
        reference_service.import_reference_pdf(state.project_id, 1, str(non_pdf))
