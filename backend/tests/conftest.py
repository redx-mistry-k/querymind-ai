from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


@pytest.fixture(scope="session")
def client(tmp_path_factory) -> TestClient:
    root = tmp_path_factory.mktemp("api-workspace")
    settings = Settings(
        root_dir=root,
        data_dir=root / "data",
        demo_db_path=root / "data" / "demo" / "querymind_demo.db",
        metadata_db_path=root / "data" / "querymind.db",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def demo_path(tmp_path: Path) -> Path:
    from backend.app.services.database.demo import create_demo_database

    return create_demo_database(tmp_path / "demo.db")
