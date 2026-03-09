# app/models/telemetry.py

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TelemetryRow(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    DO: Mapped[float] = mapped_column(Float, nullable=False)
    MLSS: Mapped[float] = mapped_column(Float, nullable=False)
    temp: Mapped[float] = mapped_column(Float, nullable=False)
    pH: Mapped[float] = mapped_column(Float, nullable=False)
    air_flow: Mapped[float] = mapped_column(Float, nullable=False)
    power: Mapped[float] = mapped_column(Float, nullable=False)
    energy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pump_hz: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    def __repr__(self) -> str:
        return (
            f"TelemetryRow(id={self.id!r}, ts={self.ts!r}, "
            f"DO={self.DO!r}, MLSS={self.MLSS!r}, temp={self.temp!r}, "
            f"pH={self.pH!r}, air_flow={self.air_flow!r}, "
            f"power={self.power!r}, energy={self.energy!r}),"
            f"pump_hz={self.pump_hz!r})"
        )
