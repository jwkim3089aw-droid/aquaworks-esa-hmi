# app/services/telemetry_store.py
from __future__ import annotations

from collections import deque
from datetime import datetime
import math  # [ADDED]

from app.schemas.telemetry import Telemetry


# Telemetry 값에 대한 하드 범위 (stream/state.py와 개념 일치)
DO_MIN, DO_MAX = 0.0, 20.0           # mg/L
MLSS_MIN, MLSS_MAX = 200.0, 20000.0  # mg/L
TEMP_MIN, TEMP_MAX = 0.0, 60.0       # °C
PH_MIN, PH_MAX = 0.0, 14.0           # pH
AIR_MIN, AIR_MAX = 0.0, 5000.0       # L/min
PWR_MIN, PWR_MAX = 0.0, 500.0        # kW

WARMUP_SAMPLES: int = 3  # [ADDED] 앞의 N개 샘플 버리기


def _is_finite(x: float) -> bool:  # [ADDED]
    return not (math.isnan(x) or math.isinf(x))


def _in_range(v: float, lo: float, hi: float) -> bool:  # [ADDED]
    return _is_finite(v) and lo <= v <= hi


def _is_plausible(row: Telemetry) -> bool:  # [ADDED]
    """Telemetry 한 샘플이 물리적으로 타당한지 검사."""
    return (
        _in_range(row.DO, DO_MIN, DO_MAX)
        and _in_range(row.MLSS, MLSS_MIN, MLSS_MAX)
        and _in_range(row.temp, TEMP_MIN, TEMP_MAX)
        and _in_range(row.pH, PH_MIN, PH_MAX)
        and _in_range(row.air_flow, AIR_MIN, AIR_MAX)
        and _in_range(row.power, PWR_MIN, PWR_MAX)
    )


class TelemetryStore:
    def __init__(self, maxlen: int = 10_000):
        self._buf: deque[Telemetry] = deque(maxlen=maxlen)
        self._seen: int = 0  # [ADDED] 들어온 샘플 총 개수

    async def add(self, row: Telemetry) -> None:
        """Telemetry 추가.
        - 앞 WARMUP_SAMPLES 개는 워밍업으로 버린다.
        - 물리적으로 불가능한 값이 하나라도 있으면 샘플 전체를 무시한다.
        """
        self._seen += 1
        if self._seen <= WARMUP_SAMPLES:
            return
        if not _is_plausible(row):
            return
        self._buf.append(row)

    async def last(self) -> Telemetry | None:
        return self._buf[-1] if self._buf else None

    async def snapshot(self, since: datetime) -> list[Telemetry]:
        return [r for r in self._buf if r.ts >= since]


# 싱글톤 DI
_store = TelemetryStore()


def get_store() -> TelemetryStore:
    return _store
