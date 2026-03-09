# app/adapters/plc/modbus/rtu_simulator.py
# [REFACTORED] Modbus RTU 시뮬레이터 서버 (C# 메모리 맵 호환, Pylance 경고 최소화)
from __future__ import annotations

import asyncio
import math
import os
from dataclasses import dataclass
from time import time
from typing import List, Optional, Sequence, Protocol, runtime_checkable, cast, Any

# --- pymodbus: 모듈 단위 임포트 ---
import pymodbus.datastore as pmds  # pyright: ignore[reportMissingTypeStubs]
from pymodbus.framer import FramerType
from pymodbus.server import StartAsyncSerialServer  # pyright: ignore[reportUnknownVariableType]

# --- C# 기반 최신 메모리 맵 주소 정의 ---
COIL_EMERGENCY = 0
COIL_PUMP_POWER = 1
COIL_PUMP_AUTO = 2
COIL_VALVE_POWER = 3
COIL_VALVE_AUTO = 4

HR_DO = 0
HR_MLSS = 1
HR_TEMP = 2
HR_PH = 3
HR_AIR_FLOW = 4
HR_POWER = 5
HR_PUMP_HZ_CURRENT = 6

HR_PUMP_SET_HZ = 13  # HMI/C#에서 명령을 내리는 주파수 주소

UNIT_ID: int = 1  # 단일 슬레이브 ID


# =========================
# 유틸리티 함수
# =========================
def s100(val: float) -> int:
    return int(val * 100)


def s10(val: float) -> int:
    return int(val * 10)


def clamp_u16(val: int) -> int:
    return max(0, min(65535, val))


# =========================
# 타입 프로토콜(우리 쪽 인터페이스)
# =========================
@runtime_checkable
class _Store(Protocol):
    def getValues(self, fx: int, address: int, count: int) -> List[int]: ...
    def setValues(self, fx: int, address: int, values: Sequence[int]) -> None: ...


@runtime_checkable
class _ServerCtx(Protocol):
    def __getitem__(self, unit_id: int) -> _Store: ...


# =========================
# 설정
# =========================
@dataclass
class RTUSimConfig:
    port: str = "COM9"
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"  # 'N'|'E'|'O'
    stopbits: int = 1
    poll_ms: int = 500  # 내부 업데이트 주기(ms)


# =========================
# 데이터스토어 구성
# =========================
def _make_context() -> _ServerCtx:
    # C# 메모리 맵은 Coils와 Holding Registers(HR)만 사용합니다.
    di = pmds.ModbusSequentialDataBlock(0, [0] * 100)  # pyright: ignore
    co = pmds.ModbusSequentialDataBlock(0, [0] * 100)  # pyright: ignore
    hr = pmds.ModbusSequentialDataBlock(0, [0] * 100)  # pyright: ignore
    ir = pmds.ModbusSequentialDataBlock(0, [0] * 100)  # pyright: ignore

    _MSC: Any = getattr(pmds, "ModbusSlaveContext")  # pyright: ignore
    slave: _Store = cast(_Store, _MSC(di=di, co=co, hr=hr, ir=ir, zero_mode=True))

    _MSCtx: Any = getattr(pmds, "ModbusServerContext")  # pyright: ignore
    ctx: _ServerCtx = cast(_ServerCtx, _MSCtx({UNIT_ID: slave}, False))

    # --- 초기값 세팅 ---
    _set_co(ctx, COIL_PUMP_POWER, 1)
    _set_co(ctx, COIL_PUMP_AUTO, 1)
    _set_co(ctx, COIL_VALVE_POWER, 1)
    _set_co(ctx, COIL_VALVE_AUTO, 1)

    _set_hr(ctx, HR_DO, clamp_u16(s100(2.0)))
    _set_hr(ctx, HR_MLSS, clamp_u16(3000))
    _set_hr(ctx, HR_TEMP, clamp_u16(s100(22.5)))
    _set_hr(ctx, HR_PH, clamp_u16(s100(7.0)))
    _set_hr(ctx, HR_AIR_FLOW, clamp_u16(s10(15.0)))
    _set_hr(ctx, HR_POWER, clamp_u16(s100(3.5)))
    _set_hr(ctx, HR_PUMP_HZ_CURRENT, clamp_u16(s10(40.0)))
    _set_hr(ctx, HR_PUMP_SET_HZ, clamp_u16(s10(40.0)))  # 설정 주파수 초기값 40.0Hz

    return ctx


# =========================
# 컨텍스트 헬퍼
# =========================
def _store(ctx: _ServerCtx) -> _Store:
    return ctx[UNIT_ID]


def _set_co(ctx: _ServerCtx, addr: int, value: int | bool) -> None:
    _store(ctx).setValues(1, addr, [1 if value else 0])


def _get_hr(ctx: _ServerCtx, addr: int, count: int = 1) -> List[int]:
    return _store(ctx).getValues(3, addr, count)


def _set_hr(ctx: _ServerCtx, addr: int, value: int | List[int]) -> None:
    vals: List[int] = value if isinstance(value, list) else [value]
    _store(ctx).setValues(3, addr, vals)


# =========================
# 시뮬레이션 루프 (아름다운 사인파 복구!)
# =========================
async def _sim_loop(ctx: _ServerCtx, dt: float) -> None:
    t0 = time()
    while True:
        await asyncio.sleep(dt)
        el = time() - t0
        phase = 2.0 * math.pi * (el / 60.0)

        # HMI에서 내린 명령(설정값)을 Holding Register에서 읽어옵니다.
        hz_set = _get_hr(ctx, HR_PUMP_SET_HZ, 1)[0] / 10.0

        # 현재 상태값을 Holding Register에서 읽어옵니다. (기존엔 IR에서 읽었음)
        air_now = _get_hr(ctx, HR_AIR_FLOW, 1)[0] / 10.0
        do_now = _get_hr(ctx, HR_DO, 1)[0] / 100.0
        pwr_now = _get_hr(ctx, HR_POWER, 1)[0] / 100.0
        mlss_now = int(_get_hr(ctx, HR_MLSS, 1)[0])
        temp_now = _get_hr(ctx, HR_TEMP, 1)[0] / 100.0
        ph_now = _get_hr(ctx, HR_PH, 1)[0] / 100.0

        # 물리 모델 수식 (사인파 + 설정 주파수 비례)
        air_next = max(0.0, air_now + 0.15 * (15.0 - air_now) + 0.10 * math.sin(phase))
        do_base = 1.2 + 0.5 * (hz_set - 30.0) / 30.0
        do_next = max(0.0, do_now + 0.20 * (do_base - do_now) + 0.05 * math.sin(phase * 1.3))
        pwr_base = 2.6 + (hz_set / 60.0) ** 3 * 1.2
        pwr_next = pwr_now + 0.25 * (pwr_base - pwr_now)
        mlss_next = int(max(0, mlss_now + 5.0 * math.sin(phase / 2.0)))
        temp_next = temp_now + 0.02 * math.sin(phase / 3.0)
        ph_next = ph_now + 0.005 * math.sin(phase / 4.0)

        # 계산된 다음 값을 다시 Holding Register에 씁니다.
        _set_hr(ctx, HR_AIR_FLOW, clamp_u16(s10(air_next)))
        _set_hr(ctx, HR_DO, clamp_u16(s100(do_next)))
        _set_hr(ctx, HR_POWER, clamp_u16(s100(pwr_next)))
        _set_hr(ctx, HR_MLSS, clamp_u16(mlss_next))
        _set_hr(ctx, HR_TEMP, clamp_u16(s100(temp_next)))
        _set_hr(ctx, HR_PH, clamp_u16(s100(ph_next)))

        # 펌프 현재 Hz도 설정값 근처에서 흔들리게 표현
        current_hz_next = hz_set + 0.2 * math.sin(phase * 2.5)
        _set_hr(ctx, HR_PUMP_HZ_CURRENT, clamp_u16(s10(current_hz_next)))


# =========================
# 서버 기동
# =========================
async def run_rtu_sim(
    port: Optional[str] = None,
    baudrate: Optional[int] = None,
    bytesize: Optional[int] = None,
    parity: Optional[str] = None,
    stopbits: Optional[int] = None,
    poll_ms: Optional[int] = None,
) -> None:
    cfg = RTUSimConfig(
        port=port or os.getenv("MODBUS_SERIAL", "COM9"),
        baudrate=int(baudrate or os.getenv("MODBUS_BAUD", 9600)),
        bytesize=int(bytesize or os.getenv("MODBUS_BYTESIZE", 8)),
        parity=(parity or os.getenv("MODBUS_PARITY", "N")).upper(),
        stopbits=int(stopbits or os.getenv("MODBUS_STOPBITS", 1)),
        poll_ms=int(poll_ms or os.getenv("MODBUS_POLL_MS", 500)),
    )

    context = _make_context()
    sim_task = asyncio.create_task(_sim_loop(context, cfg.poll_ms / 1000.0))
    print(f"🚀 Modbus RTU Simulator Started on {cfg.port} (Baud: {cfg.baudrate})")

    try:
        await StartAsyncSerialServer(
            context=context,  # type: ignore[arg-type]
            framer=FramerType.RTU,
            port=cfg.port,
            baudrate=cfg.baudrate,
            bytesize=cfg.bytesize,
            parity=cfg.parity,
            stopbits=cfg.stopbits,
            handle_local_echo=False,
            timeout=1,
            retries=3,
            retry_on_empty=True,
        )
    finally:
        sim_task.cancel()
        try:
            await sim_task
        except asyncio.CancelledError:
            pass


# =========================
# CLI
# =========================
if __name__ == "__main__":
    import argparse
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    ap = argparse.ArgumentParser(description="Modbus RTU Simulator")
    ap.add_argument("--port", default=os.getenv("MODBUS_SERIAL", "COM9"))
    ap.add_argument("--baudrate", type=int, default=int(os.getenv("MODBUS_BAUD", 9600)))
    ap.add_argument("--bytesize", type=int, default=int(os.getenv("MODBUS_BYTESIZE", 8)))
    ap.add_argument("--parity", default=os.getenv("MODBUS_PARITY", "N"))
    ap.add_argument("--stopbits", type=int, default=int(os.getenv("MODBUS_STOPBITS", 1)))
    ap.add_argument("--poll-ms", type=int, default=int(os.getenv("MODBUS_POLL_MS", 500)))
    args = ap.parse_args()

    try:
        asyncio.run(
            run_rtu_sim(
                port=args.port,
                baudrate=args.baudrate,
                bytesize=args.bytesize,
                parity=args.parity,
                stopbits=args.stopbits,
                poll_ms=args.poll_ms,
            )
        )
    except KeyboardInterrupt:
        print("\n🛑 RTU Simulator Stopped.")
