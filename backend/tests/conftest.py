from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qnu_copilot.app import create_app
from qnu_copilot.services.contracts import ContractParserService
from qnu_copilot.services.references import ReferenceService
from qnu_copilot.services.workspace import WorkspaceManager


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "runtime"


@pytest.fixture()
def workspace_manager(data_root: Path) -> WorkspaceManager:
    return WorkspaceManager(data_root)


@pytest.fixture()
def contract_parser(workspace_manager: WorkspaceManager) -> ContractParserService:
    return ContractParserService(workspace_manager)


@pytest.fixture()
def reference_service(
    workspace_manager: WorkspaceManager,
    contract_parser: ContractParserService,
) -> ReferenceService:
    return ReferenceService(workspace_manager, contract_parser)


@pytest.fixture()
def app(data_root: Path):
    return create_app(data_root)


@pytest.fixture()
def client(app) -> TestClient:
    return TestClient(app)
