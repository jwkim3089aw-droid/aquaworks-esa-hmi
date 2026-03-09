# app/adapters/historian/sqlalchemy_historian.py

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.engine import Result  # [REMOVED] 더 이상 직접 사용 안 함

from app.domain.ports import HistorianPort
from app.models.telemetry import TelemetryRow
from app.schemas.telemetry import Telemetry


class SqlAlchemyHistorian(HistorianPort):
    def __init__(self, session: AsyncSession):
        self.session: AsyncSession = session  # [UNCHANGED]

    async def write(self, sample: Telemetry) -> None:
        row = TelemetryRow(
            ts=sample.ts,
            DO=sample.DO,
            MLSS=sample.MLSS,
            temp=sample.temp,
            pH=sample.pH,
            air_flow=sample.air_flow,
            power=sample.power,
            energy=sample.energy,
        )
        self.session.add(row)
        await self.session.commit()

    async def write_many(self, samples: Sequence[Telemetry]) -> None:
        rows: list[TelemetryRow] = [
            TelemetryRow(
                ts=s.ts,
                DO=s.DO,
                MLSS=s.MLSS,
                temp=s.temp,
                pH=s.pH,
                air_flow=s.air_flow,
                power=s.power,
                energy=s.energy,
            )
            for s in samples
        ]
        self.session.add_all(rows)
        await self.session.commit()

    async def query(self, since: datetime) -> list[Telemetry]:
        stmt = (
            select(TelemetryRow)
            .where(TelemetryRow.ts >= since)
            .order_by(TelemetryRow.ts.asc())
        )
        res = await self.session.execute(stmt)  # [CHANGED] 타입 힌트 제거
        rows: Sequence[TelemetryRow] = res.scalars().all()  # [UNCHANGED or ADDED 타입 힌트만]

        return [
            Telemetry(
                ts=r.ts,
                DO=r.DO,
                MLSS=r.MLSS,
                temp=r.temp,
                pH=r.pH,
                air_flow=r.air_flow,
                power=r.power,
                energy=r.energy,
            )
            for r in rows
        ]
