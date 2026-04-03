from __future__ import annotations

import asyncio
import inspect
import logging
import sys
import time
from typing import Any, List, Optional, Awaitable, TypeVar, overload, TypeGuard
from pymodbus.client import AsyncModbusTcpClient

from app.core.device_config import get_device_config
from app.stream.state import ingest_q, db_q, Sample, get_sys_state
from app.adapters.plc.modbus.map import (
    COIL_EMERGENCY,
    COIL_PUMP_POWER,
    COIL_PUMP_AUTO,
    COIL_VALVE_POWER,
    COIL_VALVE_AUTO,
)

logger = logging.getLogger("telemetry.modbus_tcp")
logger.setLevel(logging.INFO)

T = TypeVar("T")


def _is_awaitable(x: object) -> TypeGuard[Awaitable[Any]]:
    return inspect.isawaitable(x)


@overload
async def _maybe_await(x: Awaitable[T]) -> T: ...
@overload
async def _maybe_await(x: T) -> T: ...
async def _maybe_await(x: Any) -> Any:
    if _is_awaitable(x):
        return await x
    return x


async def get_modbus_config(rtu_id: int):
    try:
        config = get_device_config(rtu_id)
        if config and config.get("host"):
            return {
                "host": config["host"],
                "port": int(config.get("port", 5020)),
                "unit_id": int(config.get("unit_id", 1)),
            }
    except Exception as e:
        logger.error(f"[RTU {rtu_id}] Config Read Error: {e}")
    return None


def _decode_sample(rtu_id: int, regs: List[int]) -> Sample:
    def safe_get(idx, div=1.0):
        return (regs[idx] / div) if regs and len(regs) > idx else 0.0

    return Sample(
        rtu_id=rtu_id,
        ts=time.time(),
        do=safe_get(0, 100.0),
        mlss=safe_get(1, 1.0),
        temp=safe_get(2, 100.0),
        ph=safe_get(3, 100.0),
        air_flow=safe_get(4, 10.0),
        valve_pos=safe_get(5, 1.0),
        pump_hz=safe_get(6, 10.0),
        power=safe_get(7, 100.0),
        energy_kwh=safe_get(9, 10.0),
    )


_write_clients = {}


async def write_hr_single(rtu_id: int, addr: int, val: float | int) -> bool:
    conf = await get_modbus_config(rtu_id)
    if not conf:
        return False

    host_port = f"{conf['host']}:{conf['port']}"

    # 캐시에 없으면 새로 생성 후 연결
    if host_port not in _write_clients:
        _write_clients[host_port] = AsyncModbusTcpClient(host=conf["host"], port=conf["port"])
        await _maybe_await(_write_clients[host_port].connect())

    client = _write_clients[host_port]

    # 끊어졌으면 슬쩍 다시 연결
    if not getattr(client, "connected", False):
        await _maybe_await(client.connect())

    try:
        # 연결 닫기(close) 없이 바로 쏘기만 함! (속도 100배 향상)
        await _maybe_await(
            client.write_register(address=addr, value=int(val), slave=conf["unit_id"])
        )
        logger.info(f"✅ [RTU {rtu_id} Write] Addr: {addr}, Val: {int(val)}")
        return True
    except Exception as e:
        logger.error(f"[RTU {rtu_id}] Write Error: {e}")
        # 에러가 났을 때만 선을 뽑고 캐시에서 지움 (다음 번에 다시 꽂도록)
        await _maybe_await(client.close())
        if host_port in _write_clients:
            del _write_clients[host_port]
        return False


async def modbus_poller_loop(rtu_id: int) -> None:
    logger.info(f"🚀 Modbus TCP Worker Started for RTU [{rtu_id}]")
    client: Any = None
    current_host, current_port = "", 0

    target_state = get_sys_state(rtu_id)

    while True:
        conf = await get_modbus_config(rtu_id)
        if not conf:
            if client:
                await _maybe_await(client.close())
                client = None
            await asyncio.sleep(2)
            continue

        if (not client) or (conf["host"] != current_host) or (conf["port"] != current_port):
            if client:
                await _maybe_await(client.close())
            current_host, current_port = conf["host"], conf["port"]
            client = AsyncModbusTcpClient(host=current_host, port=current_port, timeout=2.0)
            logger.info(f"📡 [RTU {rtu_id}] Connecting Modbus TCP: {current_host}:{current_port}")

        try:
            if not getattr(client, "connected", False):
                await _maybe_await(client.connect())

            if getattr(client, "connected", False):
                unit_id = conf["unit_id"]

                rc = await _maybe_await(client.read_coils(address=0, count=10, slave=unit_id))
                rr = await _maybe_await(
                    client.read_holding_registers(address=0, count=64, slave=unit_id)
                )

                rc_err = getattr(rc, "isError", lambda: True)() if hasattr(rc, "isError") else True
                rr_err = getattr(rr, "isError", lambda: True)() if hasattr(rr, "isError") else True

                if not rc_err and not rr_err:
                    coils = getattr(rc, "bits", [])
                    regs = getattr(rr, "registers", [])

                    if coils:
                        target_state.emergency = bool(coils[COIL_EMERGENCY])
                        target_state.pump_power = bool(coils[COIL_PUMP_POWER])
                        target_state.pump_auto = bool(coils[COIL_PUMP_AUTO])
                        target_state.valve_power = bool(coils[COIL_VALVE_POWER])
                        target_state.valve_auto = bool(coils[COIL_VALVE_AUTO])

                    if regs:
                        sample = _decode_sample(rtu_id, regs)

                        target_state.last_do = sample.do
                        target_state.last_temp = sample.temp
                        target_state.last_mlss = sample.mlss
                        target_state.last_ph = sample.ph
                        target_state.last_valve_pos = sample.valve_pos
                        target_state.last_hz = sample.pump_hz  # 🚀 AI 상태 동기화 추가!

                        try:
                            ingest_q.put_nowait(sample)
                            db_q.put_nowait(sample)
                        except asyncio.QueueFull:
                            pass
                else:
                    logger.warning(f"⚠️ [RTU {rtu_id}] 서버가 응답을 거부했습니다. (Read Error)")

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"[RTU {rtu_id}] Modbus TCP Error: {e}")
            if client:
                await _maybe_await(client.close())
                client = None
            await asyncio.sleep(2.0)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(modbus_poller_loop(rtu_id=1))
