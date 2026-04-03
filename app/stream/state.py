# app/stream/state.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Deque, Dict, List, Tuple, Any
from collections import deque
import asyncio
import math
from time import strftime, localtime


@dataclass
class Sample:
    ts: float
    do: float
    mlss: float
    temp: float
    ph: float
    air_flow: float
    power: float
    energy_kwh: float | None = None
    pump_hz: float = 0.0
    valve_pos: float = 0.0
    rtu_id: int = 1  # 🚀 다중 장비 식별자 (기본값 1)


# 🚀 [빅데이터 기반 AI 로깅] AI 연산 결과를 담을 데이터 클래스 추가
@dataclass
class AILog:
    ts: float
    rtu_id: int
    target_do: float
    curr_do: float
    temp: float
    mlss: float
    ph: float
    current_valve: float
    current_hz: float
    ai_proposed_hz: float
    final_hz: float


# ==========================================================
# 전역 큐 (Queue)
# ==========================================================
ingest_q: "asyncio.Queue[Sample]" = asyncio.Queue(maxsize=2000)
db_q: "asyncio.Queue[Sample]" = asyncio.Queue(maxsize=5000)
command_q: "asyncio.Queue[tuple[int, str, float]]" = asyncio.Queue(maxsize=100)

# 🚀 [빅데이터 기반 AI 로깅] 전용 큐 추가 (메모리 폭주 방지)
ai_log_q: "asyncio.Queue[AILog]" = asyncio.Queue(maxsize=5000)

# ==========================================================
# 차트 데이터용 메모리 버퍼 (다중 장비 분리)
# ==========================================================
BUFFER_MAXLEN: int = 10_000

_ts_bufs: Dict[int, Deque[float]] = {}
_data_bufs: Dict[int, Dict[str, Deque[float]]] = {}
_stop_event: asyncio.Event = asyncio.Event()


def _init_buffers_for_rtu(rtu_id: int):
    if rtu_id not in _ts_bufs:
        _ts_bufs[rtu_id] = deque(maxlen=BUFFER_MAXLEN)
        _data_bufs[rtu_id] = {
            "do": deque(maxlen=BUFFER_MAXLEN),
            "mlss": deque(maxlen=BUFFER_MAXLEN),
            "temp": deque(maxlen=BUFFER_MAXLEN),
            "ph": deque(maxlen=BUFFER_MAXLEN),
            "air_flow": deque(maxlen=BUFFER_MAXLEN),
            "power": deque(maxlen=BUFFER_MAXLEN),
            "energy": deque(maxlen=BUFFER_MAXLEN),
            "pump_hz": deque(maxlen=BUFFER_MAXLEN),
            "valve_pos": deque(maxlen=BUFFER_MAXLEN),
        }


def _fmt_ts(ts: float) -> str:
    return strftime("%H:%M:%S", localtime(ts))


def _is_finite(x: float) -> bool:
    return not (math.isnan(x) or math.isinf(x))


# 🚀 [핵심 패치] UI 호출 규격에 맞춰 (rtu_id, n) 순서 유지
def get_last(rtu_id: int, n: int) -> Tuple[List[str], Dict[str, List[float]]]:
    if rtu_id not in _ts_bufs:
        return [], {}

    n = max(1, min(n, BUFFER_MAXLEN))
    ts_list = list(_ts_bufs[rtu_id])[-n:]
    xs = [_fmt_ts(ts) for ts in ts_list]

    out: Dict[str, List[float]] = {}
    for k, dq in _data_bufs[rtu_id].items():
        arr = list(dq)[-n:]
        if len(arr) < len(xs):
            arr = [float("nan")] * (len(xs) - len(arr)) + arr
        out[k] = arr
    return xs, out


# ==========================================================
# 시스템 제어 상태 저장소 (실시간 제어용)
# ==========================================================
class SystemState:
    def __init__(self):
        self.auto_mode: bool = False
        self.target_do: float = 2.0
        self.target_valve: float = 80.0

        self.last_do: float = 0.0
        self.last_ts: float = 0.0
        self.last_temp: float = 0.0
        self.last_mlss: float = 0.0
        self.last_ph: float = 0.0
        self.last_valve_pos: float = 0.0
        self.last_hz: float = 0.0  # 🎯 AI 판단을 위한 펌프 현재 상태

        self.error_sum: float = 0.0  # 🚀 [STEP 1 패치] 밸브 PI 제어용 적분항 누적 변수

        self.emergency: bool = False
        self.pump_power: bool = False
        self.pump_auto: bool = False
        self.valve_power: bool = False
        self.valve_auto: bool = False


sys_states: Dict[int, SystemState] = {}


def get_sys_state(rtu_id: int) -> SystemState:
    if rtu_id not in sys_states:
        sys_states[rtu_id] = SystemState()
    return sys_states[rtu_id]


# 기존 단일 장비 코드를 위한 하위 호환성 (안전장치)
sys_state = get_sys_state(1)


# ==========================================================
# 데이터 라우터 (Ingest -> Buffer & DB)
# ==========================================================
async def bus_router(poll_timeout: float = 0.5) -> None:
    while not _stop_event.is_set():
        try:
            s: Sample = await asyncio.wait_for(ingest_q.get(), timeout=poll_timeout)

            rtu_id = s.rtu_id
            _init_buffers_for_rtu(rtu_id)
            state = get_sys_state(rtu_id)

            _ts_bufs[rtu_id].append(s.ts)
            _data_bufs[rtu_id]["do"].append(s.do)
            _data_bufs[rtu_id]["mlss"].append(s.mlss)
            _data_bufs[rtu_id]["temp"].append(s.temp)
            _data_bufs[rtu_id]["ph"].append(s.ph)
            _data_bufs[rtu_id]["air_flow"].append(s.air_flow)
            _data_bufs[rtu_id]["power"].append(s.power)
            _data_bufs[rtu_id]["pump_hz"].append(s.pump_hz)
            _data_bufs[rtu_id]["valve_pos"].append(s.valve_pos)

            val_e = s.energy_kwh if s.energy_kwh is not None else 0.0
            _data_bufs[rtu_id]["energy"].append(val_e)

            state.last_do = s.do
            state.last_ts = s.ts
            state.last_temp = s.temp
            state.last_mlss = s.mlss
            state.last_ph = s.ph
            state.last_valve_pos = s.valve_pos
            state.last_hz = s.pump_hz  # 🎯 상태 최신화 동기화 완료

            await db_q.put(s)
            ingest_q.task_done()

        except asyncio.TimeoutError:
            continue


def stop_bus() -> None:
    _stop_event.set()
