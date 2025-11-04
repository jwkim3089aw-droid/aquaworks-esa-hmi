# app/adapters/historian/sqlalchemy_historian.py
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports import HistorianPort
from app.models.telemetry import TelemetryRow
from app.schemas.telemetry import Telemetry


class SqlAlchemyHistorian(HistorianPort):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def write(self, sample: Telemetry) -> None:
        row = TelemetryRow(
            ts=sample.ts,
            DO=sample.DO,
            MLSS=sample.MLSS,
            temp=sample.temp,
            pH=sample.pH,
            air_flow=sample.air_flow,
            power=sample.power,
            total_energy_calc=sample.total_energy_calc,
        )
        self.session.add(row)
        await self.session.commit()

    async def write_many(self, samples: Sequence[Telemetry]) -> None:
        rows = [
            TelemetryRow(
                ts=s.ts,
                DO=s.DO,
                MLSS=s.MLSS,
                temp=s.temp,
                pH=s.pH,
                air_flow=s.air_flow,
                power=s.power,
                total_energy_calc=s.total_energy_calc,
            )
            for s in samples
        ]
        self.session.add_all(rows)
        await self.session.commit()

    async def query(self, since: datetime) -> list[Telemetry]:
        stmt = select(TelemetryRow).where(TelemetryRow.ts >= since).order_by(TelemetryRow.ts.asc())
        res = await self.session.execute(stmt)
        rows = res.scalars().all()
        return [
            Telemetry(
                ts=r.ts,
                DO=r.DO,
                MLSS=r.MLSS,
                temp=r.temp,
                pH=r.pH,
                air_flow=r.air_flow,
                power=r.power,
                total_energy_calc=r.total_energy_calc,
            )
            for r in rows
        ]
