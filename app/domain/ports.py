# app/domain/ports.py
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.schemas.telemetry import Telemetry


class HistorianPort(Protocol):
    async def write(self, sample: Telemetry) -> None: ...
    async def write_many(self, samples: Sequence[Telemetry]) -> None: ...
    async def query(self, since: datetime) -> list[Telemetry]: ...


class CommandPort(Protocol):
    async def apply(self, unit_id: str, kind: str, value: float) -> bool: ...
