# app/models/telemetry.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, Float, Integer
from app.db.session import Base

class TelemetryRow(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    DO: Mapped[float] = mapped_column(Float)
    MLSS: Mapped[float] = mapped_column(Float)
    temp: Mapped[float] = mapped_column(Float)
    pH: Mapped[float] = mapped_column(Float)
    air_flow: Mapped[float] = mapped_column(Float)
    power: Mapped[float] = mapped_column(Float)
    total_energy_calc: Mapped[float] = mapped_column(Float, default=0.0)
