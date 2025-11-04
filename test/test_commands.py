# test/test_commands.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import init_db
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, Generator, Dict, Any   # [CHANGED] Generator 추가
from unittest.mock import MagicMock

client = TestClient(app)

@pytest.fixture(scope="module")
async def setup_db() -> AsyncGenerator[None, None]:
    await init_db()
    yield

@pytest.fixture
def mock_session() -> Generator[MagicMock, None, None]:   # [CHANGED] MagicMock -> Generator[MagicMock, None, None]
    mock = MagicMock(spec=AsyncSession)
    yield mock

@pytest.mark.asyncio
async def test_air_setpoint(
    setup_db: AsyncGenerator[None, None],
    mock_session: MagicMock,                               # [CHANGED] AsyncSession -> MagicMock
):
    data: Dict[str, Any] = {
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
    mock_session: MagicMock,                               # [CHANGED] AsyncSession -> MagicMock
):
    response = client.get("/api/v1/commands")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
