from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


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


def build_manual_bibtex_payload() -> str:
    return """
@article{manual1,
  author = {Zhang San and Li Si},
  title = {Manual Paper One},
  journal = {Journal of Testing},
  year = {2024}
}

@inproceedings{manual2,
  author = {Wang Wu},
  title = {Manual Paper Two},
  booktitle = {Proceedings of DemoConf},
  year = {2023}
}
""".strip()


def write_pdf(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def create_project(client: TestClient, *, need_reference_recommendation: bool = True) -> dict:
    response = client.post(
        "/projects",
        json={
            "title": "Water Quality",
            "core_idea": "Build a guided thesis workflow backend.",
            "need_reference_recommendation": need_reference_recommendation,
            "minimum_required_references": 2,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_post_project_then_get_project(client: TestClient) -> None:
    created = create_project(client)
    fetched = client.get(f"/projects/{created['project_id']}")

    assert fetched.status_code == 200
    assert fetched.json()["project_id"] == created["project_id"]


def test_list_projects_returns_recent_projects(client: TestClient) -> None:
    create_project(client)
    create_project(client)
    response = client.get("/projects")

    assert response.status_code == 200
    assert len(response.json()["projects"]) == 2


def test_recommendation_import_updates_state_and_snapshots(client: TestClient) -> None:
    created = create_project(client)
    response = client.post(
        f"/projects/{created['project_id']}/references/recommendations/import",
        json={"raw_text": build_recommendation_payload()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 30
    assert body["workflow_stage"] == "pdf_processing"
    assert body["parse_result"]["raw_snapshot_path"]
    assert body["state"]["references"]["recommended_items"][0]["status"] == "pending"


def test_reference_recommendation_prompt_route_returns_prompt(client: TestClient) -> None:
    created = create_project(client)

    response = client.get(
        f"/projects/{created['project_id']}/prompts/references/recommendation"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["prompt_name"] == "reference_recommendation_prompt"
    assert "papers" in body["prompt_text"]
    assert body["prompt_snapshot_path"]


def test_skip_then_import_two_pdfs_keeps_contiguous_numbering(
    client: TestClient,
    tmp_path: Path,
) -> None:
    created = create_project(client)
    project_id = created["project_id"]
    client.post(
        f"/projects/{project_id}/references/recommendations/import",
        json={"raw_text": build_recommendation_payload()},
    )
    skip_response = client.post(
        f"/projects/{project_id}/references/1/skip",
        json={"reason": "unavailable"},
    )
    assert skip_response.status_code == 200

    pdf_1 = write_pdf(tmp_path / "中文论文2.pdf", b"pdf-two")
    pdf_2 = write_pdf(tmp_path / "English Paper 1.pdf", b"pdf-three")
    import_1 = client.post(
        f"/projects/{project_id}/references/2/pdf",
        json={"pdf_path": str(pdf_1)},
    )
    import_2 = client.post(
        f"/projects/{project_id}/references/16/pdf",
        json={"pdf_path": str(pdf_2)},
    )

    assert import_1.status_code == 200
    assert import_2.status_code == 200
    assert Path(import_1.json()["item"]["processed_pdf_path"]).name.startswith("01_")
    assert Path(import_2.json()["item"]["processed_pdf_path"]).name.startswith("02_")


def test_batch_import_returns_review_items(client: TestClient, tmp_path: Path) -> None:
    created = create_project(client)
    project_id = created["project_id"]
    client.post(
        f"/projects/{project_id}/references/recommendations/import",
        json={"raw_text": build_recommendation_payload()},
    )
    matching = write_pdf(tmp_path / "中文论文1.pdf", b"pdf-one")
    unmatched = write_pdf(tmp_path / "unknown.pdf", b"pdf-two")

    response = client.post(
        f"/projects/{project_id}/references/pdfs/batch",
        json={"pdf_paths": [str(unmatched), str(matching)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["processed_items"]) == 1
    assert len(body["review_items"]) == 1


def test_contract_parse_route_supports_all_contracts(client: TestClient) -> None:
    payloads = {
        "reference_recommendation": build_recommendation_payload(),
        "outline": json.dumps(
            {
                "title": "Demo",
                "outline": [
                    {"id": "1", "level": 1, "title": "Intro", "children": []},
                    {"id": "2", "level": 1, "title": "Method", "children": []},
                    {"id": "3", "level": 1, "title": "Conclusion", "children": []},
                ],
            }
        ),
        "chunk_plan": json.dumps(
            {
                "total_blocks": 1,
                "blocks": [
                    {
                        "block_index": 1,
                        "title": "Block",
                        "outline_node_ids": ["1"],
                        "goal": "Goal",
                        "minimum_words": 1000,
                        "citation_focus": [],
                    }
                ],
            }
        ),
        "block_content": json.dumps(
            {
                "block_index": 1,
                "block_title": "Block",
                "content": [{"type": "p", "text": "Paragraph"}],
            }
        ),
        "compressed_context": json.dumps(
            {
                "covered_blocks": [1],
                "compressed_context": {
                    "narrative_summary": "Summary",
                    "key_claims": [],
                    "used_citations": [],
                    "pending_topics": [],
                    "style_constraints": [],
                },
            }
        ),
    }

    for contract_type, raw_text in payloads.items():
        response = client.post(
            f"/contracts/{contract_type}/parse",
            json={"raw_text": raw_text},
        )
        assert response.status_code == 200
        assert response.json()["contract_type"] == contract_type


def test_outline_import_and_confirm_routes(client: TestClient, tmp_path: Path) -> None:
    created = create_project(client)
    project_id = created["project_id"]
    client.post(
        f"/projects/{project_id}/references/recommendations/import",
        json={"raw_text": build_recommendation_payload()},
    )
    pdf_1 = write_pdf(tmp_path / "中文论文1.pdf", b"pdf-one")
    pdf_2 = write_pdf(tmp_path / "中文论文2.pdf", b"pdf-two")
    client.post(
        f"/projects/{project_id}/references/1/pdf",
        json={"pdf_path": str(pdf_1)},
    )
    client.post(
        f"/projects/{project_id}/references/2/pdf",
        json={"pdf_path": str(pdf_2)},
    )

    outline_prompt = client.get(f"/projects/{project_id}/prompts/outline")
    assert outline_prompt.status_code == 200
    assert "outline" in outline_prompt.json()["prompt_text"]

    import_response = client.post(
        f"/projects/{project_id}/outline/import",
        json={"raw_text": build_outline_payload()},
    )
    assert import_response.status_code == 200
    assert import_response.json()["workflow_stage"] == "outline_editing"

    outline_tree = import_response.json()["state"]["outline"]["confirmed_tree"]
    outline_tree["outline"][0]["title"] = "绪论（确认）"
    confirm_response = client.put(
        f"/projects/{project_id}/outline/confirmed",
        json={"outline_tree": outline_tree},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["workflow_stage"] == "chunk_planning"


def test_chunk_plan_prompt_and_generation_routes(client: TestClient, tmp_path: Path) -> None:
    created = create_project(client)
    project_id = created["project_id"]
    client.post(
        f"/projects/{project_id}/references/recommendations/import",
        json={"raw_text": build_recommendation_payload()},
    )
    pdf_1 = write_pdf(tmp_path / "中文论文1.pdf", b"pdf-one")
    pdf_2 = write_pdf(tmp_path / "中文论文2.pdf", b"pdf-two")
    client.post(f"/projects/{project_id}/references/1/pdf", json={"pdf_path": str(pdf_1)})
    client.post(f"/projects/{project_id}/references/2/pdf", json={"pdf_path": str(pdf_2)})
    outline_import = client.post(
        f"/projects/{project_id}/outline/import",
        json={"raw_text": build_outline_payload()},
    )
    outline_tree = outline_import.json()["state"]["outline"]["confirmed_tree"]
    client.put(
        f"/projects/{project_id}/outline/confirmed",
        json={"outline_tree": outline_tree},
    )

    chunk_prompt = client.get(f"/projects/{project_id}/prompts/chunk-plan")
    assert chunk_prompt.status_code == 200
    assert "total_blocks" in chunk_prompt.json()["prompt_text"]

    chunk_import = client.post(
        f"/projects/{project_id}/chunk-plan/import",
        json={"raw_text": build_chunk_plan_payload()},
    )
    assert chunk_import.status_code == 200
    confirmed_plan = chunk_import.json()["state"]["chunk_plan"]["normalized_json"]
    chunk_confirm = client.put(
        f"/projects/{project_id}/chunk-plan/confirmed",
        json={"chunk_plan": confirmed_plan},
    )
    assert chunk_confirm.status_code == 200
    assert chunk_confirm.json()["workflow_stage"] == "block_generation"

    block_prompt = client.get(f"/projects/{project_id}/prompts/blocks/1/generate")
    assert block_prompt.status_code == 200
    block_import = client.post(
        f"/projects/{project_id}/blocks/1/import",
        json={"raw_text": build_block_payload(1, "绪论与背景")},
    )
    assert block_import.status_code == 200

    compress_prompt = client.get(f"/projects/{project_id}/prompts/blocks/1/compress")
    assert compress_prompt.status_code == 200
    compress_import = client.post(
        f"/projects/{project_id}/blocks/1/compressed-context/import",
        json={"raw_text": build_compressed_context_payload()},
    )
    assert compress_import.status_code == 200
    assert compress_import.json()["state"]["generation"]["current_block_index"] == 2


def test_manual_bibtex_import_route_updates_state(client: TestClient) -> None:
    created = create_project(client, need_reference_recommendation=False)
    project_id = created["project_id"]

    response = client.post(
        f"/projects/{project_id}/references/bibtex/import",
        json={"raw_text": build_manual_bibtex_payload()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 2
    assert len(body["state"]["references"]["bibtex_entries"]) == 2


def test_export_docx_route_generates_output_and_updates_state(
    client: TestClient,
    tmp_path: Path,
) -> None:
    created = create_project(client)
    project_id = created["project_id"]
    client.post(
        f"/projects/{project_id}/references/recommendations/import",
        json={"raw_text": build_recommendation_payload()},
    )
    pdf_1 = write_pdf(tmp_path / "中文论文1.pdf", b"pdf-one")
    pdf_2 = write_pdf(tmp_path / "中文论文2.pdf", b"pdf-two")
    client.post(f"/projects/{project_id}/references/1/pdf", json={"pdf_path": str(pdf_1)})
    client.post(f"/projects/{project_id}/references/2/pdf", json={"pdf_path": str(pdf_2)})
    outline_import = client.post(
        f"/projects/{project_id}/outline/import",
        json={"raw_text": build_outline_payload()},
    )
    outline_tree = outline_import.json()["state"]["outline"]["confirmed_tree"]
    client.put(
        f"/projects/{project_id}/outline/confirmed",
        json={"outline_tree": outline_tree},
    )
    chunk_import = client.post(
        f"/projects/{project_id}/chunk-plan/import",
        json={"raw_text": build_chunk_plan_payload()},
    )
    confirmed_plan = chunk_import.json()["state"]["chunk_plan"]["normalized_json"]
    client.put(
        f"/projects/{project_id}/chunk-plan/confirmed",
        json={"chunk_plan": confirmed_plan},
    )
    client.post(
        f"/projects/{project_id}/blocks/1/import",
        json={"raw_text": build_block_payload(1, "绪论与背景")},
    )
    client.post(
        f"/projects/{project_id}/blocks/1/compressed-context/import",
        json={"raw_text": build_compressed_context_payload()},
    )
    client.post(
        f"/projects/{project_id}/blocks/2/import",
        json={"raw_text": build_block_payload(2, "方法与结论")},
    )

    response = client.post(
        f"/projects/{project_id}/export/docx",
        json={"output_filename": "demo_export"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_stage"] == "done"
    assert Path(body["output_path"]).exists()
    assert Path(body["log_path"]).exists()
    assert body["reference_count"] == 2
