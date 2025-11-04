# app/schemas/telemetry.py

from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class Telemetry(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    DO: float
    MLSS: float
    temp: float
    pH: float
    air_flow: float
    power: float
    total_energy_calc: float = 0.0
