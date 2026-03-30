from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qnu_copilot.services.workspace import WorkspaceManager


class BackupService:
    """Service for managing state backups and migrations."""

    CURRENT_VERSION = "1.1"

    VERSION_MIGRATIONS: dict[str, dict[str, Any]] = {
        "1.0": {
            "export_history": [],  # Add export_history field
        },
    }

    def __init__(self, workspace_manager: WorkspaceManager) -> None:
        self.workspace_manager = workspace_manager

    def create_backup(self, project_id: str) -> Path | None:
        """Create a backup of the current state."""
        state_path = self.workspace_manager.get_state_path(project_id)
        if not state_path.exists():
            return None

        try:
            backup_dir = state_path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"state.backup_{timestamp}.json"

            shutil.copy2(state_path, backup_path)
            return backup_path
        except Exception:
            return None

    def restore_from_backup(self, project_id: str, backup_path: Path) -> bool:
        """Restore state from a backup file."""
        state_path = self.workspace_manager.get_state_path(project_id)
        if not backup_path.exists():
            return False

        try:
            shutil.copy2(backup_path, state_path)
            return True
        except Exception:
            return False

    def list_backups(self, project_id: str) -> list[dict[str, Any]]:
        """List all available backups for a project."""
        state_path = self.workspace_manager.get_state_path(project_id)
        backup_dir = state_path.parent / "backups"

        if not backup_dir.exists():
            return []

        backups = []
        for backup_file in sorted(backup_dir.glob("state.backup_*.json"), reverse=True):
            try:
                stat = backup_file.stat()
                backups.append({
                    "path": str(backup_file),
                    "filename": backup_file.name,
                    "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "size_bytes": stat.st_size,
                })
            except Exception:
                continue

        return backups

    def migrate_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Migrate state to the current schema version."""
        current_version = state.get("schema_version", "1.0")
        
        if current_version == self.CURRENT_VERSION:
            return state

        # Apply migrations in order
        for version in sorted(self.VERSION_MIGRATIONS.keys()):
            if self._compare_versions(version, current_version) > 0:
                state = self._apply_migration(state, version)

        # Update version
        state["schema_version"] = self.CURRENT_VERSION
        return state

    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compare two version strings. Returns 1 if v1 > v2, -1 if v1 < v2, 0 if equal."""
        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]
        
        for p1, p2 in zip(parts1, parts2):
            if p1 > p2:
                return 1
            if p1 < p2:
                return -1
        return 0

    def _apply_migration(self, state: dict[str, Any], version: str) -> dict[str, Any]:
        """Apply a specific migration to the state."""
        migrations = self.VERSION_MIGRATIONS.get(version, {})
        
        for field, default_value in migrations.items():
            if field not in state:
                state[field] = default_value

        return state

    def validate_state(self, state: dict[str, Any]) -> list[str]:
        """Validate state structure and return list of issues."""
        issues = []

        required_fields = [
            "schema_version",
            "project_id",
            "workflow_stage",
            "project",
            "references",
            "outline",
            "chunk_plan",
            "generation",
            "export",
        ]

        for field in required_fields:
            if field not in state:
                issues.append(f"Missing required field: {field}")

        # Validate export history
        if "export" in state and "history" not in state["export"]:
            issues.append("Missing export.history field")

        return issues
