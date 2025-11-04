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

router = APIRouter(prefix="/api/v1", tags=["telemetry"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
StoreDep = Annotated[TelemetryStore, Depends(get_store)]

# --- Historian은 구현 전까지 주석/보류 ---
# from app.domain.ports import HistorianPort
# from app.adapters.historian.sqlalchemy_historian import SqlAlchemyHistorian
# def get_historian(session: SessionDep) -> HistorianPort:
#     return SqlAlchemyHistorian(session)


@router.get("/last")
async def get_last(
    store: StoreDep,
    settings: Annotated[Settings, Depends(get_settings)],
):
    last = await store.last()
    return {} if last is None else last.model_dump()


@router.get("/telemetry")
async def get_telemetry(
    store: StoreDep,
    settings: Annotated[Settings, Depends(get_settings)],
    hours: float = 1.0,
):
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = await store.snapshot(since)
    return [r.model_dump() for r in rows]


@router.post("/telemetry", status_code=204)
async def post_telemetry(
    payload: Telemetry,
    store: StoreDep,
    settings: Annotated[Settings, Depends(get_settings)],
):
    await store.add(payload)
    return Response(status_code=204)


@router.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket, store: StoreDep):
    await ws.accept()
    try:
        while True:
            last = await store.last()
            await ws.send_json({} if last is None else last.model_dump())
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass


@router.get("/trend")
async def get_trend(
    store: StoreDep,
    fields: str | None = None,
    hours: float = 1.0,
    bucket_sec: int | None = None,  # TODO: 버킷 평균은 추후 구현
):
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = await store.snapshot(since)
    out = [r.model_dump() for r in rows]

    # 필드 필터링
    if fields:
        wanted = set(f.strip() for f in fields.split(",") if f.strip())
        for d in out:
            for k in list(d.keys()):
                if k not in wanted and k != "ts":
                    d.pop(k, None)

    # TODO: bucket_sec가 주어지면 ts를 bucket_sec로 그룹핑해서 평균/마지막값 집계
    return out


async def simulator_task(store: TelemetryStore, interval_sec: float = 1.0):
    phase = 0.0
    while True:
        now = datetime.now(UTC)
        DO = 1.8 + 0.4 * math.sin(phase) + random.uniform(-0.05, 0.05)
        MLSS = 3500 + 150 * math.sin(phase / 10.0) + random.uniform(-40, 40)
        temp = 22.0 + 1.0 * math.sin(phase / 90.0) + random.uniform(-0.1, 0.1)
        pH = 6.9 + 0.15 * math.sin(phase / 70.0) + random.uniform(-0.02, 0.02)
        air = 180 + 20 * math.sin(phase / 5.0) + random.uniform(-3, 3)
        power = max(0.6, 0.004 * (air**1.3) + random.uniform(-0.05, 0.05))

        await store.add(
            Telemetry(
                ts=now,
                DO=max(0.0, DO),
                MLSS=max(500.0, MLSS),
                temp=temp,
                pH=pH,
                air_flow=max(0.0, air),
                power=power,
                total_energy_calc=0.0,
            )
        )
        phase += 0.10
        await asyncio.sleep(interval_sec)
