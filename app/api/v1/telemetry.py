# app/api/v1/telemetry.py
from __future__ import annotations

import asyncio
import math
import random
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.schemas.telemetry import Telemetry
from app.services.telemetry_store import TelemetryStore, get_store

# 🚀 [패치] 라우터 Prefix에 기본적으로 rtu_id를 포함하도록 설계 가능하지만,
# 기존 구조 호환을 위해 각 엔드포인트에 명시적으로 추가합니다.
router = APIRouter(prefix="/api/v1", tags=["telemetry"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
StoreDep = Annotated[TelemetryStore, Depends(get_store)]


@router.get("/{rtu_id}/last")
async def get_last(
    rtu_id: int,
    store: StoreDep,
    settings: Annotated[Settings, Depends(get_settings)],
):
    # 🚀 Store가 rtu_id별로 데이터를 구분해서 가져오도록 파라미터 전달
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
    # 🚀 특정 RTU의 데이터로 저장
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


# (시뮬레이터 태스크는 백엔드 엔진에서 처리하므로 호환성 유지를 위해 남겨둠)
async def simulator_task(store: TelemetryStore, interval_sec: float = 1.0, rtu_id: int = 1):
    phase = 0.0
    while True:
        now = datetime.now(UTC)
        do_val = max(0.0, min(8.0, 1.5 + 0.8 * math.sin(phase) + random.uniform(-0.15, 0.15)))
        mlss_val = max(
            200.0,
            min(10000.0, 3500.0 + 700.0 * math.sin(phase / 8.0) + random.uniform(-200.0, 200.0)),
        )
        temp_val = max(
            5.0, min(40.0, 20.0 + 4.0 * math.sin(phase / 24.0) + random.uniform(-0.5, 0.5))
        )
        ph_val = max(
            6.0, min(8.5, 7.0 + 0.3 * math.sin(phase / 18.0) + random.uniform(-0.05, 0.05))
        )
        air_val = max(
            50.0, min(400.0, 180.0 + 60.0 * math.sin(phase / 5.0) + random.uniform(-5.0, 5.0))
        )
        power_val = max(
            0.3, min(20.0, 2.0 + 0.01 * max(0.0, air_val - 120.0) + random.uniform(-0.2, 0.2))
        )

        await store.add(
            rtu_id=rtu_id,
            payload=Telemetry(
                ts=now,
                DO=do_val,
                MLSS=mlss_val,
                temp=temp_val,
                pH=ph_val,
                air_flow=air_val,
                power=power_val,
                energy=0.0,
            ),
        )
        phase += 0.10
        await asyncio.sleep(interval_sec)
