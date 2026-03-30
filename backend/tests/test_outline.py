from __future__ import annotations

import json
from pathlib import Path

import pytest

from qnu_copilot.domain.models import ProjectInfo
from qnu_copilot.services.errors import ConflictError
from qnu_copilot.services.outline import OutlineService
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


def build_outline_payload() -> str:
    return json.dumps(
        {
            "title": "Water Quality Thesis",
            "outline": [
                {
                    "id": "1",
                    "level": 1,
                    "title": "绪论",
                    "children": [
                        {"id": "1.1", "level": 2, "title": "研究背景", "children": []}
                    ],
                },
                {"id": "2", "level": 1, "title": "系统设计", "children": []},
                {"id": "3", "level": 1, "title": "实验与结论", "children": []},
            ],
        },
        ensure_ascii=False,
    )


def write_pdf(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def setup_project(
    workspace_manager: WorkspaceManager,
    reference_service: ReferenceService,
    tmp_path: Path,
) -> str:
    state, _ = workspace_manager.create_project(
        ProjectInfo(
            title="Outline Project",
            core_idea="Outline import should follow PDF processing.",
            need_reference_recommendation=True,
        ),
        template_id="qnu-undergraduate-v1",
        minimum_required_references=2,
    )
    reference_service.import_recommendations(state.project_id, build_recommendation_payload())
    pdf_1 = write_pdf(tmp_path / "中文论文1.pdf", b"pdf-one")
    pdf_2 = write_pdf(tmp_path / "中文论文2.pdf", b"pdf-two")
    reference_service.import_reference_pdf(state.project_id, 1, str(pdf_1))
    reference_service.import_reference_pdf(state.project_id, 2, str(pdf_2))
    return state.project_id


def test_outline_import_requires_minimum_processed_pdfs(
    workspace_manager: WorkspaceManager,
    contract_parser,
) -> None:
    state, _ = workspace_manager.create_project(
        ProjectInfo(
            title="Outline Conflict",
            core_idea="Need PDFs first.",
            need_reference_recommendation=False,
        ),
        template_id="qnu-undergraduate-v1",
        minimum_required_references=1,
    )
    outline_service = OutlineService(workspace_manager, contract_parser)

    with pytest.raises(ConflictError):
        outline_service.import_outline(state.project_id, build_outline_payload())


def test_outline_import_and_confirm_updates_state(
    workspace_manager: WorkspaceManager,
    reference_service: ReferenceService,
    contract_parser,
    tmp_path: Path,
) -> None:
    project_id = setup_project(workspace_manager, reference_service, tmp_path)
    outline_service = OutlineService(workspace_manager, contract_parser)

    outline_service.import_outline(project_id, build_outline_payload())
    state = workspace_manager.load_state(project_id)
    assert state.workflow_stage.value == "outline_editing"
    assert state.outline.status.value == "ready"
    assert state.outline.confirmed_tree is not None
    first_node = state.outline.confirmed_tree["outline"][0]
    assert first_node["enabled"] is True

    confirmed_tree = state.outline.confirmed_tree
    confirmed_tree["outline"][0]["title"] = "绪论（已确认）"
    outline_service.confirm_outline(project_id, confirmed_tree)
    confirmed_state = workspace_manager.load_state(project_id)
    assert confirmed_state.workflow_stage.value == "chunk_planning"
    assert confirmed_state.outline.status.value == "completed"
    assert confirmed_state.outline.confirmed_tree["outline"][0]["title"] == "绪论（已确认）"
