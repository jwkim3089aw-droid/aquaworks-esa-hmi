# app/services/telemetry_store.py
from __future__ import annotations
from collections import deque
from datetime import datetime
from typing import Deque, List, Optional
from app.schemas.telemetry import Telemetry

class TelemetryStore:
    def __init__(self, maxlen: int = 10_000):
        self._buf: Deque[Telemetry] = deque(maxlen=maxlen)

    async def add(self, row: Telemetry) -> None:
        self._buf.append(row)

    async def last(self) -> Optional[Telemetry]:
        return self._buf[-1] if self._buf else None

    async def snapshot(self, since: datetime) -> List[Telemetry]:
        return [r for r in self._buf if r.ts >= since]

# 싱글톤 DI
_store = TelemetryStore()

def get_store() -> TelemetryStore:
    return _store
