# app/adapters/plc/modbus/simulator.py
# Modbus TCP 시뮬레이터 (pymodbus 3.11.x / DeviceContext / unit 1·0·255 / zero_mode / Pylance strict-quiet)
from __future__ import annotations

import asyncio, math, os, logging, builtins as _bi, importlib
from dataclasses import dataclass
from time import time
from typing import Any, List, Optional, TextIO, Dict, cast

# ----- 로그 즉시 플러시 -----
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True
)
logging.getLogger("pymodbus").setLevel(logging.INFO)


def _p(
    *a: object, sep: str = " ", end: str = "\n", file: Optional[TextIO] = None, flush: bool = True
) -> None:
    _bi.print(*a, sep=sep, end=end, file=file, flush=flush)


# ----- 런타임 동적 로더 (pymodbus 3.11.x용; Pylance 엄격에서도 조용) -----
def _resolve_modbus() -> tuple[Any, Any, Any, Any, Any]:
    """
    Returns:
      (ModbusServerContext, ModbusDeviceContext,
       ModbusSequentialDataBlock, StartAsyncTcpServer, FramerType)
    """
    # datastore 심볼
    ds = importlib.import_module("pymodbus.datastore")
    ModbusServerContext: Any = getattr(ds, "ModbusServerContext", None)
    ModbusDeviceContext: Any = getattr(ds, "ModbusDeviceContext", None)
    ModbusSequentialDataBlock: Any = getattr(ds, "ModbusSequentialDataBlock", None)

    if not (ModbusServerContext and ModbusDeviceContext and ModbusSequentialDataBlock):
        # 하위 모듈 분기 재시도
        try:
            ds_ctx = importlib.import_module("pymodbus.datastore.context")
            ds_store = importlib.import_module("pymodbus.datastore.store")
            ModbusServerContext = ModbusServerContext or getattr(
                ds_ctx, "ModbusServerContext", None
            )
            ModbusDeviceContext = ModbusDeviceContext or getattr(
                ds_ctx, "ModbusDeviceContext", None
            )
            ModbusSequentialDataBlock = ModbusSequentialDataBlock or getattr(
                ds_store, "ModbusSequentialDataBlock", None
            )
        except Exception:
            pass
    if not (ModbusServerContext and ModbusDeviceContext and ModbusSequentialDataBlock):
        raise RuntimeError("Unsupported pymodbus install: datastore classes not found")

    # 서버 시작자
    StartAsyncTcpServer: Any = None
    try:
        srv = importlib.import_module("pymodbus.server")
        StartAsyncTcpServer = getattr(srv, "StartAsyncTcpServer", None)
    except Exception:
        StartAsyncTcpServer = None
    if StartAsyncTcpServer is None:
        try:
            srv_async = importlib.import_module("pymodbus.server.async_io")
            StartAsyncTcpServer = getattr(srv_async, "StartAsyncTcpServer", None)
        except Exception:
            StartAsyncTcpServer = None
    if StartAsyncTcpServer is None:
        raise RuntimeError("Unsupported pymodbus install: StartAsyncTcpServer not found")

    # 프레이머 타입
    fr = importlib.import_module("pymodbus.framer")
    FramerType: Any = getattr(fr, "FramerType", None)
    if FramerType is None:
        raise RuntimeError("Unsupported pymodbus install: FramerType not found")

    return (
        ModbusServerContext,
        ModbusDeviceContext,
        ModbusSequentialDataBlock,
        StartAsyncTcpServer,
        FramerType,
    )


_ModbusServerContext, _ModbusDeviceContext, _SeqBlock, StartAsyncTcpServer, FramerType = (
    _resolve_modbus()
)

from .map import (
    IR_DO,
    IR_MLSS,
    IR_TEMP,
    IR_PH,
    IR_AIR_FLOW,
    IR_POWER,
    IR_PUMP_HZ,
    HR_AIR_SET,
    HR_PUMP_HZ,
    IR_SIZE,
    HR_SIZE,
    s100,
    s10,
    clamp_u16,
    DEFAULTS,
)

UNIT_PRIMARY: int = 1


@dataclass
class TCPSimConfig:
    host: str = "127.0.0.1"
    port: int = 5020
    poll_ms: int = 500


# ----- 컨텍스트 구성 (DeviceContext + zero_mode) -----
def _build_ctx_objects() -> tuple[Any, Any]:
    di: Any = _SeqBlock(0, [0] * 64)
    co: Any = _SeqBlock(0, [0] * 64)
    hr: Any = _SeqBlock(0, [0] * HR_SIZE)
    ir: Any = _SeqBlock(0, [0] * IR_SIZE)

    # DeviceContext 사용, zero_mode 안전 처리
    try:
        dev_ctx: Any = _ModbusDeviceContext(di=di, co=co, hr=hr, ir=ir, zero_mode=True)
    except TypeError:
        dev_ctx = _ModbusDeviceContext(di=di, co=co, hr=hr, ir=ir)
        try:
            setattr(dev_ctx, "zero_mode", True)
        except Exception:
            pass

    _p(f"[SIM] device zero_mode={getattr(dev_ctx, 'zero_mode', None)}")

    dev_map: Dict[int, Any] = {UNIT_PRIMARY: dev_ctx, 0: dev_ctx, 255: dev_ctx}

    # 3.11.x: devices= 권장 → 실패 시 순차 백포트
    try:
        srv_ctx: Any = _ModbusServerContext(devices=dev_map, single=False)
    except TypeError:
        try:
            srv_ctx = _ModbusServerContext(slaves=dev_map, single=False)
        except TypeError:
            srv_ctx = _ModbusServerContext(dev_map, False)
    return srv_ctx, dev_ctx


def _make_context() -> Any:
    ctx, _ = _build_ctx_objects()
    _set_ir(ctx, IR_DO, clamp_u16(s100(float(DEFAULTS.do))))
    _set_ir(ctx, IR_MLSS, clamp_u16(int(DEFAULTS.mlss)))
    _set_ir(ctx, IR_TEMP, clamp_u16(s100(float(DEFAULTS.temp))))
    _set_ir(ctx, IR_PH, clamp_u16(s100(float(DEFAULTS.ph))))
    _set_ir(ctx, IR_AIR_FLOW, clamp_u16(s10(float(DEFAULTS.air_flow))))
    _set_ir(ctx, IR_POWER, clamp_u16(s100(float(DEFAULTS.power))))
    _set_ir(ctx, IR_PUMP_HZ, clamp_u16(s10(float(DEFAULTS.pump_hz))))
    _set_hr(ctx, HR_AIR_SET, clamp_u16(s10(float(DEFAULTS.air_set))))
    _set_hr(ctx, HR_PUMP_HZ, clamp_u16(s10(float(DEFAULTS.pump_hz))))
    return ctx


# ----- 내부 접근 헬퍼 -----
def _store(ctx: Any, unit: int = UNIT_PRIMARY) -> Any:
    try:
        return ctx[unit]
    except Exception:
        return ctx[UNIT_PRIMARY]


def _get_ir(ctx: Any, addr: int, count: int = 1) -> List[int]:
    return cast(List[int], _store(ctx).getValues(4, addr, count))


def _set_ir(ctx: Any, addr: int, value: int | List[int]) -> None:
    vals: List[int] = value if isinstance(value, list) else [value]
    _store(ctx).setValues(4, addr, vals)


def _get_hr(ctx: Any, addr: int, count: int = 1) -> List[int]:
    return cast(List[int], _store(ctx).getValues(3, addr, count))


def _set_hr(ctx: Any, addr: int, value: int | List[int]) -> None:
    vals: List[int] = value if isinstance(value, list) else [value]
    _store(ctx).setValues(3, addr, vals)


# ----- 동특성 루프 -----
async def _sim_loop(ctx: Any, dt: float) -> None:
    t0 = time()
    _p("[SIM] dynamics started")
    while True:
        await asyncio.sleep(dt)
        el = time() - t0
        phase = 2.0 * math.pi * (el / 60.0)

        air_set = _get_hr(ctx, HR_AIR_SET, 1)[0] / 10.0
        hz_set = _get_hr(ctx, HR_PUMP_HZ, 1)[0] / 10.0

        air_now = _get_ir(ctx, IR_AIR_FLOW, 1)[0] / 10.0
        do_now = _get_ir(ctx, IR_DO, 1)[0] / 100.0
        pwr_now = _get_ir(ctx, IR_POWER, 1)[0] / 100.0
        mlss_now = int(_get_ir(ctx, IR_MLSS, 1)[0])
        temp_now = _get_ir(ctx, IR_TEMP, 1)[0] / 100.0
        ph_now = _get_ir(ctx, IR_PH, 1)[0] / 100.0
        hz_now = _get_ir(ctx, IR_PUMP_HZ, 1)[0] / 10.0
        hz_next = hz_now + 0.2 * (hz_set - hz_now)

        air_next = max(0.0, air_now + 0.15 * (air_set - air_now) + 0.10 * math.sin(phase))

        do_base = 1.2 + 0.5 * (hz_next - 30.0) / 30.0
        do_next = max(0.0, do_now + 0.20 * (do_base - do_now) + 0.05 * math.sin(phase * 1.3))

        pwr_base = 2.6 + (hz_next / 60.0) ** 3 * 1.2
        # [수정] Power에 sin 파동 추가 (0.15 * sin(phase * 3.0)) -> 위아래로 흔들림
        pwr_next = pwr_now + 0.25 * (pwr_base - pwr_now) + 0.15 * math.sin(phase * 3.0)

        mlss_next = int(max(0, mlss_now + 5.0 * math.sin(phase / 2.0)))
        temp_next = temp_now + 0.02 * math.sin(phase / 3.0)
        ph_next = ph_now + 0.005 * math.sin(phase / 4.0)

        _set_ir(ctx, IR_AIR_FLOW, clamp_u16(s10(air_next)))
        _set_ir(ctx, IR_DO, clamp_u16(s100(do_next)))
        _set_ir(ctx, IR_POWER, clamp_u16(s100(pwr_next)))
        _set_ir(ctx, IR_MLSS, clamp_u16(mlss_next))
        _set_ir(ctx, IR_TEMP, clamp_u16(s100(temp_next)))
        _set_ir(ctx, IR_PH, clamp_u16(s100(ph_next)))
        _set_ir(ctx, IR_PUMP_HZ, clamp_u16(s10(hz_next)))


# ----- 서버 -----
async def run_tcp_sim(
    host: Optional[str] = None, port: Optional[int] = None, poll_ms: Optional[int] = None
) -> None:
    cfg = TCPSimConfig(
        host=host or os.getenv("MODBUS_TCP_HOST", "127.0.0.1"),
        port=int(port or os.getenv("MODBUS_TCP_PORT", 5020)),
        poll_ms=int(poll_ms or os.getenv("MODBUS_POLL_MS", 500)),
    )
    ctx: Any = _make_context()
    sim_task = asyncio.create_task(_sim_loop(ctx, cfg.poll_ms / 1000.0))
    _p(f"[SIM] ModbusTCP simulator listening @ {cfg.host}:{cfg.port} (framer=SOCKET)")
    try:
        await StartAsyncTcpServer(
            context=ctx, address=(cfg.host, cfg.port), framer=FramerType.SOCKET
        )
    finally:
        sim_task.cancel()
        try:
            await sim_task
        except asyncio.CancelledError:
            pass


# ----- CLI -----
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Modbus TCP Simulator")
    ap.add_argument("--host", default=os.getenv("MODBUS_TCP_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MODBUS_TCP_PORT", 5020)))
    ap.add_argument("--poll-ms", type=int, default=int(os.getenv("MODBUS_POLL_MS", 500)))
    args = ap.parse_args()
    asyncio.run(run_tcp_sim(host=args.host, port=args.port, poll_ms=args.poll_ms))
