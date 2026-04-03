# app/workers/modbus_rtu_poller.py
from __future__ import annotations

import asyncio
import inspect
import logging
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, List, Optional, TypeVar, overload, TypeGuard

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.framer import FramerType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import engine
from app.models.settings import ConnectionConfig
from app.stream.state import ingest_q, db_q, Sample, sys_state
from app.adapters.plc.modbus.map import (
    COIL_EMERGENCY,
    COIL_PUMP_POWER,
    COIL_PUMP_AUTO,
    COIL_VALVE_POWER,
    COIL_VALVE_AUTO,
    COIL_SIZE,
    HR_EXCEPTION,
    HR_SIZE,
    HR_PUMP_FR_1,
)

# 🚀 [정석] 복잡한 핸들러 제거하고 이름만 부여합니다.
logger = logging.getLogger("telemetry.modbus_rtu")
logger.setLevel(logging.INFO)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)
T = TypeVar("T")


# ... (기존 _is_awaitable 부터 클래스 로직 전체 동일, 그대로 유지) ...
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


def _backoff_sleep(failures: int, base: float = 0.5, cap: float = 10.0) -> float:
    exp = min(max(failures, 0), 6)
    s = min(base * (2**exp), cap)
    return s + random.uniform(0.0, 0.25)


async def _call_modbus(fn, *args, unit_id: int, **kwargs):
    try:
        return await _maybe_await(fn(*args, **kwargs, slave=unit_id))
    except TypeError:
        return await _maybe_await(fn(*args, **kwargs, unit=unit_id))


@dataclass
class _ConfCache:
    value: Optional[dict]
    ts: float


class ConfigProvider:
    def __init__(self, ttl_sec: float = 1.5):
        self.ttl_sec = ttl_sec
        self._cache = _ConfCache(value=None, ts=0.0)

    async def get(self, *, force: bool = False) -> Optional[dict]:
        now = time.monotonic()
        if (not force) and self._cache.value is not None and (now - self._cache.ts) < self.ttl_sec:
            return self._cache.value

        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(ConnectionConfig).where(ConnectionConfig.id == 1)
                )
                config = res.scalar_one_or_none()
        except Exception as e:
            logger.error(f"DB Config Read Error: {e}")
            return None

        conf = None
        if config and config.host:
            conf = {
                "port": str(config.host).strip(),
                "baudrate": int(config.port or 9600),
                "unit_id": int(config.unit_id or 1),
            }

        self._cache = _ConfCache(value=conf, ts=now)
        return conf

    def invalidate(self) -> None:
        self._cache = _ConfCache(value=None, ts=0.0)


global_config_provider = ConfigProvider()


@dataclass
class RTUStats:
    read_ok: int = 0
    read_err: int = 0
    write_ok: int = 0
    write_err: int = 0
    reconnects: int = 0
    samples_pushed: int = 0
    samples_dropped: int = 0
    ingest_drop_oldest: int = 0
    db_drop_oldest: int = 0
    loop_overrun: int = 0
    last_read_ms: float = 0.0
    last_write_ms: float = 0.0
    last_log_ts: float = field(default_factory=lambda: time.monotonic())


@dataclass
class WriteReq:
    addr: int
    value: int
    fut: asyncio.Future[bool]
    ts: float


write_q: asyncio.Queue[WriteReq] = asyncio.Queue(maxsize=200)


async def write_hr_single(addr: int, val: float | int) -> bool:
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[bool] = loop.create_future()
    req = WriteReq(addr=int(addr), value=int(val), fut=fut, ts=time.monotonic())

    try:
        write_q.put_nowait(req)
    except asyncio.QueueFull:
        logger.warning("❌ [RTU Write] Queue Full -> Dropping request addr=%s", addr)
        return False

    try:
        return await asyncio.wait_for(fut, timeout=2.0)
    except asyncio.TimeoutError:
        logger.warning("⚠️ [RTU Write] Timeout addr=%s", addr)
        return False


def _queue_put_latest(q: asyncio.Queue, item: Any, *, stats: RTUStats, name: str) -> bool:
    try:
        q.put_nowait(item)
        return True
    except asyncio.QueueFull:
        try:
            _ = q.get_nowait()
            q.task_done()
        except Exception:
            pass
        if name == "ingest":
            stats.ingest_drop_oldest += 1
        elif name == "db":
            stats.db_drop_oldest += 1
        try:
            q.put_nowait(item)
            return True
        except asyncio.QueueFull:
            return False


class ModbusRTUPoller:
    def __init__(
        self,
        period_sec: float = 0.5,
        read_timeout_sec: float = 0.5,
        idle_close_sec: float = 30.0,
        stats_log_sec: float = 60.0,
        force_refresh_failures: int = 3,
    ):
        self.period = period_sec
        self.cfg = global_config_provider
        self.read_timeout = read_timeout_sec
        self.idle_close = idle_close_sec
        self.stats_log_sec = stats_log_sec
        self.force_refresh_failures = force_refresh_failures

        self.client: Any = None
        self.port: str = ""
        self.baudrate: int = 0

        self._last_io_ts = time.monotonic()
        self._failures = 0
        self._last_err_log_ts = 0.0
        self.stats = RTUStats()

    async def _close(self) -> None:
        if self.client:
            try:
                await _maybe_await(self.client.close())
            except Exception:
                pass
        self.client = None

    async def _fail_all_writes(self) -> None:
        while True:
            try:
                req = write_q.get_nowait()
            except asyncio.QueueEmpty:
                return
            if not req.fut.done():
                req.fut.set_result(False)
            try:
                write_q.task_done()
            except Exception:
                pass

    def _rate_limited_warn(self, msg: str, *args) -> None:
        now = time.monotonic()
        if now - self._last_err_log_ts >= 1.0:
            logger.warning(msg, *args)
            self._last_err_log_ts = now

    async def _ensure_client(self, conf: dict) -> None:
        port, baud = conf["port"], conf["baudrate"]
        if not port or baud <= 0:
            raise ValueError(f"Invalid config: port={port!r}, baud={baud}")

        if (not self.client) or (port != self.port) or (baud != self.baudrate):
            await self._close()
            self.port, self.baudrate = port, baud
            self.client = AsyncModbusSerialClient(
                port=port,
                baudrate=baud,
                bytesize=8,
                parity="N",
                stopbits=1,
                framer=FramerType.RTU,
                timeout=self.read_timeout,
            )
            self.stats.reconnects += 1
            logger.info("📡 Modbus RTU 접속 시도: %s @ %s", port, baud)

        if not getattr(self.client, "connected", False):
            await _maybe_await(self.client.connect())

    async def _handle_write_requests(self, conf: dict, *, budget_ms: float) -> None:
        start = time.monotonic()
        unit_id = conf["unit_id"]
        while True:
            if (time.monotonic() - start) * 1000.0 > budget_ms:
                return
            try:
                req = write_q.get_nowait()
            except asyncio.QueueEmpty:
                return

            ok = False
            try:
                await self._ensure_client(conf)
                t0 = time.monotonic()
                rr = await asyncio.wait_for(
                    _call_modbus(
                        self.client.write_register,
                        unit_id=unit_id,
                        address=req.addr,
                        value=req.value,
                    ),
                    timeout=self.read_timeout + 0.2,
                )
                self.stats.last_write_ms = (time.monotonic() - t0) * 1000.0
                if getattr(rr, "isError", lambda: False)():
                    raise RuntimeError(f"Write error: {rr}")
                ok = True
                self.stats.write_ok += 1
                self._last_io_ts = time.monotonic()
            except Exception as e:
                self.stats.write_err += 1
                self._rate_limited_warn("❌ [RTU Write] Failed addr=%s err=%s", req.addr, e)

            if not req.fut.done():
                req.fut.set_result(ok)
            try:
                write_q.task_done()
            except Exception:
                pass

    async def _read_phase(self, conf: dict) -> None:
        await self._ensure_client(conf)
        if not getattr(self.client, "connected", False):
            return

        unit_id = conf["unit_id"]
        t0 = time.monotonic()

        rc = await asyncio.wait_for(
            _call_modbus(self.client.read_coils, unit_id=unit_id, address=0, count=COIL_SIZE),
            timeout=self.read_timeout + 0.2,
        )
        rr = await asyncio.wait_for(
            _call_modbus(
                self.client.read_holding_registers, unit_id=unit_id, address=0, count=HR_SIZE
            ),
            timeout=self.read_timeout + 0.2,
        )

        self.stats.last_read_ms = (time.monotonic() - t0) * 1000.0

        if getattr(rc, "isError", lambda: True)() or getattr(rr, "isError", lambda: True)():
            raise RuntimeError("Read Error: Could not read Coils or Registers")

        coils = rc.bits[:COIL_SIZE]
        regs = rr.registers[:HR_SIZE]

        if coils[COIL_EMERGENCY]:
            logger.error("🚨 비상 정지 상태 감지됨!")

        exc_val = regs[HR_EXCEPTION]
        if exc_val & 0x0002:
            self._rate_limited_warn("⚠️ 인버터 통신 에러 발생!")
        if exc_val & 0x0004:
            self._rate_limited_warn("⚠️ 전력계 통신 에러 발생!")

        setattr(sys_state, "pump_power", coils[COIL_PUMP_POWER])
        setattr(sys_state, "pump_auto", coils[COIL_PUMP_AUTO])
        setattr(sys_state, "valve_power", coils[COIL_VALVE_POWER])
        setattr(sys_state, "valve_auto", coils[COIL_VALVE_AUTO])

        dummy_pump_hz = regs[HR_PUMP_FR_1] / 10.0 if HR_PUMP_FR_1 < len(regs) else 0.0
        sample = Sample(
            ts=time.time(),
            do=0.0,
            mlss=0.0,
            temp=0.0,
            ph=0.0,
            air_flow=0.0,
            power=0.0,
            pump_hz=dummy_pump_hz,
            energy_kwh=0.0,
        )
        ok1 = _queue_put_latest(ingest_q, sample, stats=self.stats, name="ingest")
        ok2 = _queue_put_latest(db_q, sample, stats=self.stats, name="db")

        if ok1 and ok2:
            self.stats.samples_pushed += 1
        else:
            self.stats.samples_dropped += 1

        self._last_io_ts = time.monotonic()
        self.stats.read_ok += 1

    def _log_stats(self) -> None:
        now = time.monotonic()
        if now - self.stats.last_log_ts < self.stats_log_sec:
            return
        self.stats.last_log_ts = now
        logger.info(
            "📊 RTU Stats | Read(OK=%d Err=%d Last=%.1fms) | Write(OK=%d Err=%d Last=%.1fms) | Reconn=%d",
            self.stats.read_ok,
            self.stats.read_err,
            self.stats.last_read_ms,
            self.stats.write_ok,
            self.stats.write_err,
            self.stats.last_write_ms,
            self.stats.reconnects,
        )

    async def run_forever(self) -> None:
        logger.info("🚀 Modbus RTU Worker Started (Field-Grade PCB Edition)")
        next_t = time.monotonic()

        while True:
            next_t += self.period
            force_refresh = self._failures >= self.force_refresh_failures
            conf = await self.cfg.get(force=force_refresh)

            if not conf:
                await self._close()
                await self._fail_all_writes()
                await asyncio.sleep(1.0)
                continue

            try:
                backlog = write_q.qsize()
                budget = 120.0 + min(backlog * 10.0, 180.0)
                await self._handle_write_requests(conf, budget_ms=budget)
                await self._read_phase(conf)
                self._failures = 0

                if self.idle_close > 0 and (time.monotonic() - self._last_io_ts) > self.idle_close:
                    logger.info("🧹 Client Idle Timeout -> Closing Port")
                    await self._close()

            except Exception as e:
                self.stats.read_err += 1
                self._failures += 1
                self._rate_limited_warn("⚠️ RTU Loop Error (Failures: %d): %s", self._failures, e)
                await self._close()
                if self._failures >= self.force_refresh_failures:
                    self.cfg.invalidate()
                await self._fail_all_writes()
                await asyncio.sleep(_backoff_sleep(self._failures))

            self._log_stats()
            delay = next_t - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                self.stats.loop_overrun += 1
                next_t = time.monotonic()


async def modbus_poller_loop() -> None:
    poller = ModbusRTUPoller()
    await poller.run_forever()


if __name__ == "__main__":
    # 이 파일을 단독으로 실행할 때만 콘솔에 뿌리도록 정석 처리
    logging.basicConfig(
        level=logging.INFO, format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s"
    )
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(modbus_poller_loop())
