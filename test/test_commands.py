# test/test_commands.py
from collections.abc import AsyncGenerator, Generator  # [CHANGED] Generator 추가
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import init_db
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
async def setup_db() -> AsyncGenerator[None, None]:
    await init_db()
    yield


@pytest.fixture
def mock_session() -> (
    Generator[MagicMock, None, None]
):  # [CHANGED] MagicMock -> Generator[MagicMock, None, None]
    mock = MagicMock(spec=AsyncSession)
    yield mock


@pytest.mark.asyncio
async def test_air_setpoint(
    setup_db: AsyncGenerator[None, None],
    mock_session: MagicMock,  # [CHANGED] AsyncSession -> MagicMock
):
    data: dict[str, Any] = {
        "kind": "AIR_SETPOINT",
        "value": 185.0,
        "unit_id": "blower-1",
        "dry_run": False,
        "priority": 0,
    }
    response = client.post("/api/v1/air/setpoint", json=data)
    assert response.status_code == 200
    assert response.json()["kind"] == "AIR_SETPOINT"
    assert response.json()["value"] == 185.0


@pytest.mark.asyncio
async def test_get_commands(
    setup_db: AsyncGenerator[None, None],
    mock_session: MagicMock,  # [CHANGED] AsyncSession -> MagicMock
):
    response = client.get("/api/v1/commands")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
