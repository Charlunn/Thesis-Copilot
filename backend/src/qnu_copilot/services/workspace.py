from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from qnu_copilot.domain.models import ProjectInfo, ProjectState, ReferencesState
from qnu_copilot.services.errors import NotFoundError


class WorkspaceManager:
    # Backup threshold: create backup if changes exceed this percentage
    BACKUP_THRESHOLD = 0.2  # 20% of max backup count

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.projects_root = self.data_root / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self._backup_counts: dict[str, int] = {}  # Track saves for smart backup

    def create_project(
        self,
        project_info: ProjectInfo,
        *,
        template_id: str,
        minimum_required_references: int,
    ) -> tuple[ProjectState, Path]:
        project_id = self._generate_project_id()
        project_root = self.projects_root / project_id
        self._create_project_dirs(project_root)
        state = ProjectState(
            project_id=project_id,
            template_id=template_id,
            project=project_info,
            references=ReferencesState(minimum_required=minimum_required_references),
        )
        self.save_state(project_id, state)
        return state, project_root

    def get_project_root(self, project_id: str) -> Path:
        project_root = self.projects_root / project_id
        if not project_root.exists():
            raise NotFoundError(f"project does not exist: {project_id}")
        return project_root

    def get_state_path(self, project_id: str) -> Path:
        return self.get_project_root(project_id) / "state.json"

    def get_ai_outputs_dir(self, project_id: str) -> Path:
        return self.get_project_root(project_id) / "ai_outputs"

    def load_state(self, project_id: str) -> ProjectState:
        state_path = self.get_state_path(project_id)
        if not state_path.exists():
            raise NotFoundError(f"state.json not found for project: {project_id}")
        return ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))

    def list_projects(self) -> list[tuple[ProjectState, Path]]:
        projects: list[tuple[ProjectState, Path]] = []
        for project_root in self.projects_root.iterdir():
            if not project_root.is_dir():
                continue
            state_path = project_root / "state.json"
            if not state_path.exists():
                continue
            try:
                state = ProjectState.model_validate_json(
                    state_path.read_text(encoding="utf-8")
                )
            except Exception:
                continue
            projects.append((state, project_root))
        projects.sort(key=lambda item: item[0].updated_at, reverse=True)
        return projects

    def save_state(self, project_id: str, state: ProjectState) -> Path:
        # Create smart backup at key milestones
        self._maybe_create_backup(project_id)
        
        state.touch()
        state_path = self.get_state_path(project_id)
        payload = json.dumps(
            state.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        self._atomic_write_text(state_path, payload)
        return state_path

    def _maybe_create_backup(self, project_id: str) -> None:
        """Create automatic backup at key milestones."""
        MAX_BACKUPS = 10
        
        # Key stages that trigger backup
        key_stages = [
            "references",  # After importing references
            "outline_editing",  # After confirming outline
            "chunk_planning",  # After confirming chunk plan
            "block_generation",  # After generating blocks
            "done",  # After export
        ]
        
        # Initialize backup count if needed
        if project_id not in self._backup_counts:
            self._backup_counts[project_id] = 0
        
        self._backup_counts[project_id] += 1
        
        # Create backup every 5 saves or at key milestones
        should_backup = (
            self._backup_counts[project_id] % 5 == 0 or
            self._get_current_stage(project_id) in key_stages
        )
        
        if should_backup:
            self._create_backup(project_id)
            # Clean up old backups
            self._cleanup_old_backups(project_id, MAX_BACKUPS)

    def _get_current_stage(self, project_id: str) -> str | None:
        """Get current workflow stage."""
        try:
            state = self.load_state(project_id)
            return state.workflow_stage.value if hasattr(state.workflow_stage, 'value') else str(state.workflow_stage)
        except Exception:
            return None

    def _create_backup(self, project_id: str) -> None:
        """Create a backup of the current state."""
        state_path = self.get_state_path(project_id)
        if not state_path.exists():
            return
        
        try:
            backup_dir = state_path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            stage = self._get_current_stage(project_id) or "unknown"
            backup_path = backup_dir / f"state.{stage}.{timestamp}.json"
            
            shutil.copy2(state_path, backup_path)
        except Exception:
            pass

    def _cleanup_old_backups(self, project_id: str, max_backups: int) -> None:
        """Remove old backups, keeping only the most recent ones."""
        state_path = self.get_state_path(project_id)
        backup_dir = state_path.parent / "backups"
        
        if not backup_dir.exists():
            return
        
        backups = sorted(backup_dir.glob("state.*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        for old_backup in backups[max_backups:]:
            try:
                old_backup.unlink()
            except Exception:
                pass

    def write_ai_snapshot(
        self,
        project_id: str,
        *,
        contract_name: str,
        raw_text: str,
        normalized_json_text: str | None = None,
    ) -> tuple[Path, Path | None]:
        output_dir = self.get_ai_outputs_dir(project_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        raw_path = output_dir / f"{timestamp}_{contract_name}.raw.txt"
        self._atomic_write_text(raw_path, raw_text)
        normalized_path: Path | None = None
        if normalized_json_text is not None:
            normalized_path = output_dir / f"{timestamp}_{contract_name}.normalized.json"
            self._atomic_write_text(normalized_path, normalized_json_text)
        return raw_path, normalized_path

    def write_prompt_snapshot(
        self,
        project_id: str,
        *,
        prompt_name: str,
        prompt_text: str,
    ) -> Path:
        prompt_dir = self.get_project_root(project_id) / "prompt_exports"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        prompt_path = prompt_dir / f"{timestamp}_{prompt_name}.txt"
        self._atomic_write_text(prompt_path, prompt_text)
        return prompt_path

    def _create_project_dirs(self, project_root: Path) -> None:
        project_root.mkdir(parents=True, exist_ok=False)
        for dirname in [
            "raw_pdfs",
            "processed_pdfs",
            "prompt_exports",
            "ai_outputs",
            "output",
        ]:
            (project_root / dirname).mkdir(parents=True, exist_ok=True)

    def _generate_project_id(self) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:6]
        return f"qnu-{timestamp}-{suffix}"

    def _atomic_write_text(self, target_path: Path, content: str) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=target_path.parent,
            suffix=".tmp",
        ) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        os.replace(temp_path, target_path)
