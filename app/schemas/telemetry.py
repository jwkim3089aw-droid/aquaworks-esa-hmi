# app/schemas/telemetry.py
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, ConfigDict

class Telemetry(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    DO: float
    MLSS: float
    temp: float
    pH: float
    air_flow: float
    power: float
    energy: float = 0.0

    model_config = ConfigDict(
        from_attributes=True,
    )
