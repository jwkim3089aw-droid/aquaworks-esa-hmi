# app/api/v1/telemetry.py
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.schemas.telemetry import Telemetry
from app.services.telemetry_store import TelemetryStore, get_store

router = APIRouter(prefix="/api/v1", tags=["telemetry"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
StoreDep = Annotated[TelemetryStore, Depends(get_store)]


@router.get("/{rtu_id}/last")
async def get_last(
    rtu_id: int, store: StoreDep, settings: Annotated[Settings, Depends(get_settings)]
):
    last = await store.last(rtu_id=rtu_id)
    return {} if last is None else last.model_dump()


@router.get("/{rtu_id}/telemetry")
async def get_telemetry(
    rtu_id: int,
    store: StoreDep,
    settings: Annotated[Settings, Depends(get_settings)],
    hours: float = 1.0,
):
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = await store.snapshot(rtu_id=rtu_id, since=since)
    return [r.model_dump() for r in rows]


@router.post("/{rtu_id}/telemetry", status_code=204)
async def post_telemetry(
    rtu_id: int,
    payload: Telemetry,
    store: StoreDep,
    settings: Annotated[Settings, Depends(get_settings)],
):
    await store.add(rtu_id=rtu_id, payload=payload)
    return Response(status_code=204)


@router.websocket("/ws/telemetry/{rtu_id}")
async def ws_telemetry(rtu_id: int, ws: WebSocket, store: StoreDep):
    await ws.accept()
    try:
        while True:
            last = await store.last(rtu_id=rtu_id)
            await ws.send_json({} if last is None else last.model_dump())
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@router.get("/{rtu_id}/trend")
async def get_trend(
    rtu_id: int,
    store: StoreDep,
    fields: str | None = None,
    hours: float = 1.0,
    bucket_sec: int | None = None,
):
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = await store.snapshot(rtu_id=rtu_id, since=since)
    out = [r.model_dump() for r in rows]

    if fields:
        wanted = set(f.strip() for f in fields.split(",") if f.strip())
        for d in out:
            for k in list(d.keys()):
                if k not in wanted and k != "ts":
                    d.pop(k, None)
    return out


# 🚀 [패치] 가짜 데이터 생성기 완전 삭제 (더 이상 HMI가 엉뚱한 데이터를 DB에 쑤셔넣지 않음)
async def simulator_task(store: TelemetryStore, interval_sec: float = 1.0):
    """
    이 함수는 폐기되었습니다.
    모든 물리 연산은 독립된 디지털 트윈(simulator/model.py)에서 수행되며,
    Modbus 통신을 통해 데이터가 들어와야 정상입니다.
    """
    pass
