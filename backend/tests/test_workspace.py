from __future__ import annotations

import json

from qnu_copilot.domain.models import ProjectInfo
from qnu_copilot.services.workspace import WorkspaceManager


def test_create_project_initializes_workspace_and_state(
    workspace_manager: WorkspaceManager,
) -> None:
    state, project_root = workspace_manager.create_project(
        ProjectInfo(
            title="Water Quality Monitoring",
            core_idea="Use edge devices and LoRa to monitor river quality.",
            need_reference_recommendation=True,
        ),
        template_id="qnu-undergraduate-v1",
        minimum_required_references=20,
    )

    assert state.project_id
    assert project_root.exists()
    for dirname in ["raw_pdfs", "processed_pdfs", "prompt_exports", "ai_outputs", "output"]:
        assert (project_root / dirname).exists()

    state_path = project_root / "state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["project_id"] == state.project_id
    assert payload["workflow_stage"] == "references"


def test_save_state_uses_atomic_replace(workspace_manager: WorkspaceManager) -> None:
    state, project_root = workspace_manager.create_project(
        ProjectInfo(
            title="Atomic Writes",
            core_idea="State writes must not leave partial files behind.",
            need_reference_recommendation=False,
        ),
        template_id="qnu-undergraduate-v1",
        minimum_required_references=20,
    )

    state.ui.last_route = "/projects/demo"
    state_path = workspace_manager.save_state(state.project_id, state)

    temp_files = list(project_root.glob("*.tmp"))
    assert temp_files == []
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["ui"]["last_route"] == "/projects/demo"
