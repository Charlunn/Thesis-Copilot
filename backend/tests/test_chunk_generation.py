from __future__ import annotations

import json
from pathlib import Path

from qnu_copilot.domain.models import ProjectInfo
from qnu_copilot.services.chunk_plan import ChunkPlanService
from qnu_copilot.services.generation import GenerationService
from qnu_copilot.services.outline import OutlineService
from qnu_copilot.services.prompts import PromptFactoryService
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
            "title": "Demo",
            "outline": [
                {
                    "id": "1",
                    "level": 1,
                    "title": "绪论",
                    "children": [
                        {"id": "1.1", "level": 2, "title": "背景", "children": []}
                    ],
                },
                {"id": "2", "level": 1, "title": "方法", "children": []},
                {"id": "3", "level": 1, "title": "结论", "children": []},
            ],
        },
        ensure_ascii=False,
    )


def build_chunk_plan_payload() -> str:
    return json.dumps(
        {
            "total_blocks": 2,
            "blocks": [
                {
                    "block_index": 1,
                    "title": "绪论与背景",
                    "outline_node_ids": ["1", "1.1"],
                    "goal": "交代研究背景",
                    "minimum_words": 1200,
                    "citation_focus": ["研究背景"],
                },
                {
                    "block_index": 2,
                    "title": "方法与结论",
                    "outline_node_ids": ["2", "3"],
                    "goal": "说明方法并给出结论",
                    "minimum_words": 1200,
                    "citation_focus": ["方法", "结论"],
                },
            ],
        },
        ensure_ascii=False,
    )


def build_block_payload(block_index: int, title: str) -> str:
    return json.dumps(
        {
            "block_index": block_index,
            "block_title": title,
            "content": [{"type": "p", "text": f"正文内容 {title}【文献01】"}],
        },
        ensure_ascii=False,
    )


def build_compressed_context_payload() -> str:
    return json.dumps(
        {
            "covered_blocks": [1],
            "compressed_context": {
                "narrative_summary": "前文已经完成绪论和研究背景。",
                "key_claims": ["明确了研究问题"],
                "used_citations": ["文献01"],
                "pending_topics": ["方法与结论"],
                "style_constraints": ["保持学术口吻"],
            },
        },
        ensure_ascii=False,
    )


def build_abstract_payload() -> str:
    return json.dumps(
        {
            "title": "摘要",
            "content": [
                "本文围绕目标问题构建了完整研究路径，并在文献与场景约束下给出可执行方案。",
                "结果表明该方案在可用性和一致性方面均达到预期，并为后续扩展提供基础。",
            ],
            "keywords": ["论文系统", "自动化", "工作流"],
        },
        ensure_ascii=False,
    )


def write_pdf(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def setup_project(
    workspace_manager: WorkspaceManager,
    reference_service: ReferenceService,
    outline_service: OutlineService,
    chunk_plan_service: ChunkPlanService,
    tmp_path: Path,
) -> str:
    state, _ = workspace_manager.create_project(
        ProjectInfo(
            title="Chunk Project",
            core_idea="Need chunk planning and block generation.",
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
    outline_service.import_outline(state.project_id, build_outline_payload())
    confirmed_tree = workspace_manager.load_state(state.project_id).outline.confirmed_tree
    outline_service.confirm_outline(state.project_id, confirmed_tree)
    chunk_plan_service.import_chunk_plan(state.project_id, build_chunk_plan_payload())
    chunk_plan_service.confirm_chunk_plan(
        state.project_id,
        workspace_manager.load_state(state.project_id).chunk_plan.normalized_json,
    )
    return state.project_id


def test_prompt_factory_and_generation_roundtrip(
    workspace_manager: WorkspaceManager,
    reference_service: ReferenceService,
    contract_parser,
    tmp_path: Path,
) -> None:
    outline_service = OutlineService(workspace_manager, contract_parser)
    chunk_plan_service = ChunkPlanService(workspace_manager, contract_parser)
    generation_service = GenerationService(workspace_manager, contract_parser)
    prompt_factory = PromptFactoryService(workspace_manager)
    project_id = setup_project(
        workspace_manager,
        reference_service,
        outline_service,
        chunk_plan_service,
        tmp_path,
    )

    chunk_prompt, chunk_snapshot = prompt_factory.render_chunk_plan_prompt(project_id)
    assert "total_blocks" in chunk_prompt
    assert chunk_snapshot.exists()

    block_prompt, block_snapshot = prompt_factory.render_block_generation_prompt(project_id, 1)
    assert "block_index" in block_prompt
    assert block_snapshot.exists()

    generation_service.import_block_content(
        project_id,
        1,
        build_block_payload(1, "绪论与背景"),
    )
    compress_prompt, compress_snapshot = prompt_factory.render_compress_prompt(project_id, 1)
    assert "covered_blocks" in compress_prompt
    assert compress_snapshot.exists()

    generation_service.import_compressed_context(
        project_id,
        1,
        build_compressed_context_payload(),
    )
    generation_service.import_block_content(
        project_id,
        2,
        build_block_payload(2, "方法与结论"),
    )
    generation_service.import_abstract(project_id, build_abstract_payload())

    state = workspace_manager.load_state(project_id)
    assert state.generation.current_block_index == 2
    assert state.generation.status.value == "completed"
    assert state.generation.blocks[0].compressed_context_json is not None
    assert state.generation.blocks[1].normalized_json is not None
    assert state.generation.abstract_json is not None
