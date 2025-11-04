# app/repositories/telemetry_repo.py

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import TelemetryRow
from app.schemas.telemetry import Telemetry


class TelemetryRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, t: Telemetry) -> None:
        row = TelemetryRow(**t.model_dump())
        self.session.add(row)
        await self.session.commit()

    async def latest(self) -> TelemetryRow | None:
        stmt = select(TelemetryRow).order_by(TelemetryRow.ts.desc()).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def between(self, start: datetime, stop: datetime) -> list[TelemetryRow]:
        stmt = (
            select(TelemetryRow)
            .where(TelemetryRow.ts >= start, TelemetryRow.ts < stop)
            .order_by(TelemetryRow.ts.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
