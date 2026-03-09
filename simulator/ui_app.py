# simulator/ui_app.py
from __future__ import annotations

import asyncio
import logging
import math
import os
import sys
import time
from typing import Any, Dict, Optional, TypeVar, Coroutine

from pymodbus.client import AsyncModbusTcpClient
from nicegui import app, ui

# =========================================================
# [설정] 인코딩 & 로그
# =========================================================
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int):
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.max_level


def setup_standard_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    h_out = logging.StreamHandler(sys.stdout)
    h_out.setLevel(logging.INFO)
    h_out.addFilter(MaxLevelFilter(logging.ERROR))
    h_out.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"))
    h_err = logging.StreamHandler(sys.stderr)
    h_err.setLevel(logging.ERROR)
    h_err.setFormatter(logging.Formatter("%(asctime)s | 🛑 %(levelname)-7s | %(message)s"))
    logger.addHandler(h_out)
    logger.addHandler(h_err)
    return logger


logger = setup_standard_logger("ESA_SIM_UI")

# =========================================================
# [UI/Modbus 다중 장비 설정]
# =========================================================
MODBUS_TARGETS = [
    {"esa_id": 1, "host": "127.0.0.1", "port": 5020},
    {"esa_id": 2, "host": "127.0.0.1", "port": 5021},
    {"esa_id": 3, "host": "127.0.0.1", "port": 5022},
]

MODBUS_UNIT_ID = 1
READ_INTERVAL_S = float(os.getenv("ESA_READ_INTERVAL_S", "0.5"))
WRITE_FLUSH_S = float(os.getenv("ESA_WRITE_FLUSH_S", "0.12"))

HR_READ_START = 0
HR_READ_COUNT = 8  # 🚀 [패치] 밸브(5번)와 펌프(6번)를 모두 읽기 위해 COUNT를 8로 늘림

# 🎯 [핵심 패치] HMI/시뮬레이터 C# 엔진과 주소 완벽 동기화!
HR_PUMP_SET_HZ = 29  # 🚨 기존 13에서 29로 변경!! (이게 범인이었습니다)
HR_VALVE_SET = 30  # C# 규격과 일치 (이래서 밸브는 잘 됐던 것)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "assets")
ASSET_PATH = "/assets"
app.add_static_files(ASSET_PATH, STATIC_DIR)


# =========================================================
# [Shared State 다중화] (각 ESA별로 독립적인 상태 저장소)
# =========================================================
def create_empty_sim_data() -> Dict[str, Any]:
    return {
        "DO": 0.0,
        "MLSS": 0.0,
        "Temp": 0.0,
        "pH": 0.0,
        "AirFlow": 0.0,
        "Power": 0.0,
        "Energy": 0.0,
        "PumpHz": 0.0,
        "Valve": 0.0,
        "ResetCmd": False,
        "is_connected": False,
        "last_rx_ts": 0.0,
        "last_tx_ts": 0.0,
        "write_mode": "RAW",
    }


sim_states: Dict[int, Dict[str, Any]] = {
    target["esa_id"]: create_empty_sim_data() for target in MODBUS_TARGETS
}

active_esa_id = 1


# =========================================================
# [포매터 등 유틸]
# =========================================================
def _coerce_float(x: Any) -> float | None:
    try:
        if isinstance(x, bool):
            return None
        return float(x)
    except Exception:
        return None


def fmt_raw(x: Any, spec: str) -> str:
    if x is None:
        return "None"
    v = _coerce_float(x)
    if v is None:
        return str(x)
    if math.isnan(v):
        return "NaN"
    if math.isinf(v):
        return "Inf" if v > 0 else "-Inf"
    return format(v, spec)


def raw_progress_value(x: Any) -> Any:
    v = _coerce_float(x)
    return v if v is not None else x


T = TypeVar("T")


def create_guarded_task(coro: Coroutine[Any, Any, T], name: str) -> asyncio.Task[T]:
    task: asyncio.Task[T] = asyncio.create_task(coro, name=name)

    def _done_cb(t: asyncio.Task[T]) -> None:
        try:
            exc = t.exception()
            if exc:
                logger.exception("Background task crashed: %s", name, exc_info=exc)
        except asyncio.CancelledError:
            pass

    task.add_done_callback(_done_cb)
    return task


# =========================================================
# [다중 연결 지원 Modbus Service]
# =========================================================
class MultiModbusService:
    def __init__(self):
        self._stop = asyncio.Event()
        self._tasks = []
        self.clients: Dict[int, AsyncModbusTcpClient] = {}
        self.locks: Dict[int, asyncio.Lock] = {t["esa_id"]: asyncio.Lock() for t in MODBUS_TARGETS}
        self.write_events: Dict[int, asyncio.Event] = {
            t["esa_id"]: asyncio.Event() for t in MODBUS_TARGETS
        }
        self.pending_writes: Dict[int, Dict[str, Any]] = {t["esa_id"]: {} for t in MODBUS_TARGETS}

    async def start(self):
        for target in MODBUS_TARGETS:
            esa_id = target["esa_id"]
            self._tasks.extend(
                [
                    create_guarded_task(self._connect_forever(target), f"connect_{esa_id}"),
                    create_guarded_task(self._read_loop(esa_id), f"read_{esa_id}"),
                    create_guarded_task(self._write_loop(esa_id), f"write_{esa_id}"),
                ]
            )

    async def stop(self):
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for c in self.clients.values():
            if c:
                await c.close()

    async def _set_connected(self, esa_id: int, connected: bool):
        sim_states[esa_id]["is_connected"] = connected

    async def _disconnect(self, esa_id: int):
        async with self.locks[esa_id]:
            client = self.clients.get(esa_id)
            self.clients[esa_id] = None
        if client:
            try:
                await client.close()
            except:
                pass

    async def _connect_forever(self, target: dict):
        esa_id = target["esa_id"]
        while not self._stop.is_set():
            if not sim_states[esa_id]["is_connected"]:
                try:
                    client = AsyncModbusTcpClient(host=target["host"], port=target["port"])
                    await client.connect()
                    if client.connected:
                        async with self.locks[esa_id]:
                            self.clients[esa_id] = client
                        await self._set_connected(esa_id, True)
                        logger.info(
                            f"✅ [ESA {esa_id}] 연결 성공 ({target['host']}:{target['port']})"
                        )
                except Exception:
                    await self._set_connected(esa_id, False)
                    await self._disconnect(esa_id)
            await asyncio.sleep(2.0)

    async def _read_loop(self, esa_id: int):
        while not self._stop.is_set():
            await asyncio.sleep(READ_INTERVAL_S)
            async with self.locks[esa_id]:
                client = self.clients.get(esa_id)
                connected = sim_states[esa_id]["is_connected"]

            if not connected or not client:
                continue

            try:
                rr = await client.read_holding_registers(
                    address=HR_READ_START, count=HR_READ_COUNT, slave=MODBUS_UNIT_ID
                )
                if hasattr(rr, "isError") and rr.isError():
                    raise Exception("Modbus Read Error")

                regs = rr.registers
                now = time.time()
                async with self.locks[esa_id]:
                    state = sim_states[esa_id]
                    state["DO"] = regs[0] / 100.0
                    state["MLSS"] = regs[1]
                    state["Temp"] = regs[2] / 100.0
                    state["pH"] = regs[3] / 100.0
                    state["AirFlow"] = regs[4] / 10.0
                    state["Valve"] = regs[5]  # 5번: 밸브 상태
                    state["PumpHz"] = regs[6] / 10.0  # 6번: 펌프 주파수
                    state["last_rx_ts"] = now
            except Exception as e:
                logger.error(f"❌ [ESA {esa_id}] 읽기 실패: {e}")
                await self._set_connected(esa_id, False)
                await self._disconnect(esa_id)

    async def write_immediate(self, esa_id: int, key: str, value: Any):
        async with self.locks[esa_id]:
            sim_states[esa_id][key] = value
            sim_states[esa_id]["last_tx_ts"] = time.time()
            client = self.clients.get(esa_id)
            connected = sim_states[esa_id]["is_connected"]

        if not connected or not client:
            return

        try:
            # 🎯 여기서 정의된 HR_PUMP_SET_HZ(29) 와 HR_VALVE_SET(30)을 사용합니다.
            addr = HR_PUMP_SET_HZ if key == "PumpHz" else (HR_VALVE_SET if key == "Valve" else None)
            if addr is not None:
                multiplier = 10.0 if key == "PumpHz" else 1.0
                val = int(value * multiplier)
                await client.write_register(address=addr, value=val, slave=MODBUS_UNIT_ID)
                logger.info(
                    f"✅ [SimUI Write] ESA {esa_id} {key} -> {value} (Addr: {addr}, Val: {val})"
                )
        except Exception as e:
            logger.error(f"❌ [ESA {esa_id}] 쓰기 실패: {e}")
            await self._set_connected(esa_id, False)
            await self._disconnect(esa_id)

    async def enqueue_write(self, esa_id: int, key: str, value: Any):
        async with self.locks[esa_id]:
            self.pending_writes[esa_id][key] = value
            sim_states[esa_id][key] = value
            sim_states[esa_id]["last_tx_ts"] = time.time()
        self.write_events[esa_id].set()

    async def _write_loop(self, esa_id: int):
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self.write_events[esa_id].wait(), timeout=WRITE_FLUSH_S)
            except asyncio.TimeoutError:
                pass
            self.write_events[esa_id].clear()

            if sim_states[esa_id].get("write_mode") != "COALESCE":
                continue

            async with self.locks[esa_id]:
                client = self.clients.get(esa_id)
                connected = sim_states[esa_id]["is_connected"]
                pending = dict(self.pending_writes[esa_id])
                self.pending_writes[esa_id].clear()

            if not connected or not client or not pending:
                continue

            try:
                for k, v in pending.items():
                    addr = (
                        HR_PUMP_SET_HZ
                        if k == "PumpHz"
                        else (HR_VALVE_SET if k == "Valve" else None)
                    )
                    if addr is not None:
                        multiplier = 10.0 if k == "PumpHz" else 1.0
                        val = int(v * multiplier)
                        await client.write_register(address=addr, value=val, slave=MODBUS_UNIT_ID)
            except Exception as e:
                logger.error(f"❌ [ESA {esa_id}] 쓰기 루프 에러: {e}")
                await self._set_connected(esa_id, False)
                await self._disconnect(esa_id)


modbus_service: Optional[MultiModbusService] = None


# =========================================================
# [UI Components]
# =========================================================
def glass_card(width: str = "w-[260px]"):
    return ui.column().classes(
        f"{width} bg-slate-900/80 backdrop-blur-md rounded-xl border border-slate-700/50 shadow-2xl p-5 gap-4"
    )


def sensor_row(label: str, key: str, unit: str, icon: str, color: str, spec: str):
    with ui.row().classes(
        "w-full justify-between items-center py-2 border-b border-slate-700/50 last:border-0"
    ):
        with ui.row().classes("items-center gap-3"):
            ui.icon(icon, color=color).classes("text-lg opacity-80")
            ui.label(label).classes("text-slate-400 text-xs font-bold tracking-wide")
        with ui.row().classes("items-baseline gap-1"):
            val_lbl = ui.label().classes("text-white font-mono text-lg font-bold")
            val_lbl.bind_text_from(
                sim_states,
                "active",
                backward=lambda _: fmt_raw(sim_states[active_esa_id].get(key, 0.0), spec),
            )
            ui.label(unit).classes("text-slate-500 text-[10px]")


@ui.page("/")
def simulator_ui():
    ui.colors(primary="#06b6d4", secondary="#64748B")
    bg_path = os.path.join(STATIC_DIR, "esa_sim_bg.png")
    bg_ver = (
        str(int(os.path.getmtime(bg_path))) if os.path.exists(bg_path) else str(int(time.time()))
    )

    with ui.column().classes("w-full h-screen items-center justify-center bg-black"):
        with ui.card().classes(
            "relative w-[1024px] h-[768px] p-0 bg-[#0b0f19] border border-slate-800 overflow-hidden shadow-[0_0_50px_rgba(0,0,0,0.5)]"
        ):
            ui.image(f"{ASSET_PATH}/esa_sim_bg.png?v={bg_ver}").classes(
                "w-full h-full object-cover opacity-60 absolute"
            )

            with ui.row().classes(
                "absolute top-0 w-full h-16 px-8 justify-between items-center bg-gradient-to-b from-black/80 z-10"
            ):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("hub", color="cyan").classes("text-2xl")
                    ui.label("ESA Multi-Sim Dashboard").classes(
                        "text-cyan-400 text-xl font-bold tracking-[0.2em] font-mono"
                    )

                with ui.row().classes("items-center gap-2 bg-slate-800/50 p-1 rounded-lg"):

                    def set_active_esa(esa_id):
                        global active_esa_id
                        active_esa_id = esa_id
                        sim_states["active"] = time.time()
                        update_status()

                    for target in MODBUS_TARGETS:
                        _id = target["esa_id"]
                        btn = ui.button(f"ESA {_id}", on_click=lambda id=_id: set_active_esa(id))
                        btn.props("outline color=cyan size=sm").classes("w-20 font-bold")

                with ui.row().classes("items-center gap-4"):
                    with ui.row().classes(
                        "items-center gap-2 bg-black/40 px-3 py-1 rounded-full border border-slate-700"
                    ):
                        status_dot = ui.element("div").classes("w-2 h-2 rounded-full bg-red-500")
                        status_txt = ui.label("OFFLINE").classes(
                            "text-[10px] font-bold text-red-500 font-mono"
                        )

                        def update_status():
                            is_conn = sim_states[active_esa_id].get("is_connected", False)
                            if is_conn:
                                status_dot.classes(
                                    "bg-green-500 shadow-[0_0_8px_lime]", remove="bg-red-500"
                                )
                                status_txt.set_text(f"ESA {active_esa_id} ONLINE")
                                status_txt.classes("text-green-400", remove="text-red-500")
                            else:
                                status_dot.classes(
                                    "bg-red-500", remove="bg-green-500 shadow-[0_0_8px_lime]"
                                )
                                status_txt.set_text(f"ESA {active_esa_id} OFFLINE")
                                status_txt.classes("text-red-500", remove="text-green-400")

                        ui.timer(0.5, update_status)

            # Content (센서부)
            with ui.row().classes(
                "absolute w-full h-full p-8 pt-24 justify-between items-start z-0 pointer-events-none"
            ):
                with glass_card():
                    with ui.row().classes("w-full items-center gap-2 mb-2"):
                        ui.icon("sensors", color="slate").classes("text-sm")
                        ui.label("SENSOR ARRAY").classes(
                            "text-slate-500 text-[10px] font-bold tracking-widest"
                        )
                    sensor_row("D.O.", "DO", "mg/L", "water_drop", "cyan-400", ".2f")
                    sensor_row("MLSS", "MLSS", "mg/L", "science", "green-400", ".0f")
                    sensor_row("TEMP", "Temp", "°C", "thermostat", "red-400", ".1f")
                    sensor_row("pH", "pH", "", "colorize", "yellow-400", ".2f")

                with glass_card():
                    with ui.row().classes("w-full items-center gap-2 mb-2"):
                        ui.icon("settings_suggest", color="slate").classes("text-sm")
                        ui.label("DRIVE STATUS").classes(
                            "text-slate-500 text-[10px] font-bold tracking-widest"
                        )
                    with ui.column().classes("w-full items-center py-4 relative"):
                        ui.circular_progress(
                            value=1, size="140px", color="slate-800", show_value=False
                        ).props("thickness=0.1")
                        hz_prog = (
                            ui.circular_progress(size="140px", show_value=False, color="cyan-400")
                            .classes("absolute top-4")
                            .props("thickness=0.1 cap-rounded")
                        )
                        hz_prog.bind_value_from(
                            sim_states,
                            "active",
                            backward=lambda _: raw_progress_value(
                                sim_states[active_esa_id].get("PumpHz", 0) / 60.0  # 60Hz Max
                            ),
                        )

                        with ui.column().classes(
                            "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 items-center gap-0"
                        ):
                            ui.label("JET PUMP").classes("text-[9px] text-cyan-500 font-bold mb-1")
                            val_lbl = ui.label().classes(
                                "text-3xl font-bold text-white font-mono leading-none"
                            )
                            val_lbl.bind_text_from(
                                sim_states,
                                "active",
                                backward=lambda _: fmt_raw(
                                    sim_states[active_esa_id].get("PumpHz", 0), ".1f"
                                ),
                            )
                            ui.label("Hz").classes("text-[9px] text-slate-500 font-bold mt-1")

            # Controls (제어부)
            with ui.row().classes(
                "absolute bottom-8 left-1/2 -translate-x-1/2 w-[680px] h-[88px] bg-[#151923]/90 backdrop-blur-xl rounded-2xl border border-slate-600/50 items-center px-8 gap-8 z-20 shadow-[0_10px_40px_rgba(0,0,0,0.6)] pointer-events-auto"
            ):
                # PUMP 제어 (대시보드 자체 제어 패널)
                with ui.column().classes("flex-1 gap-1"):
                    with ui.row().classes("w-full justify-between items-center"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("settings", color="cyan").classes("text-xs")
                            ui.label("JET PUMP SPEED").classes(
                                "text-[10px] text-cyan-400 font-bold tracking-wider"
                            )
                        ui.label().classes("text-white font-mono font-bold").bind_text_from(
                            sim_states,
                            "active",
                            backward=lambda _: f"{fmt_raw(sim_states[active_esa_id].get('PumpHz',0), '.1f')} Hz",
                        )

                    async def on_hz_change(value: Any) -> None:
                        if modbus_service:
                            await modbus_service.write_immediate(active_esa_id, "PumpHz", value)

                    sl_hz = (
                        ui.slider(min=0, max=60, step=0.1)
                        .classes("w-full")
                        .props("color=cyan track-color=grey-9 thumb-size=16px dense")
                    )
                    sl_hz.bind_value_from(
                        sim_states,
                        "active",
                        backward=lambda _: sim_states[active_esa_id].get("PumpHz", 0),
                    )
                    sl_hz.on(
                        "update:model-value", lambda e: asyncio.create_task(on_hz_change(e.args))
                    )

                ui.separator().props("vertical").classes("h-10 bg-slate-700")

                # VALVE 제어
                with ui.column().classes("flex-1 gap-1"):
                    with ui.row().classes("w-full justify-between items-center"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("valve", color="green").classes("text-xs")
                            ui.label("AIR VALVE POSITION").classes(
                                "text-[10px] text-green-400 font-bold tracking-wider"
                            )
                        ui.label().classes("text-white font-mono font-bold").bind_text_from(
                            sim_states,
                            "active",
                            backward=lambda _: f"{fmt_raw(sim_states[active_esa_id].get('Valve',0), '.0f')} %",
                        )

                    async def on_valve_change(value: Any) -> None:
                        if modbus_service:
                            await modbus_service.write_immediate(active_esa_id, "Valve", value)

                    sl_valve = (
                        ui.slider(min=0, max=100, step=1)
                        .classes("w-full")
                        .props("color=green track-color=grey-9 thumb-size=16px dense")
                    )
                    sl_valve.bind_value_from(
                        sim_states,
                        "active",
                        backward=lambda _: sim_states[active_esa_id].get("Valve", 0),
                    )
                    sl_valve.on(
                        "update:model-value", lambda e: asyncio.create_task(on_valve_change(e.args))
                    )


# =========================================================
# [Lifecycle]
# =========================================================
async def startup() -> None:
    global modbus_service
    modbus_service = MultiModbusService()
    await modbus_service.start()
    sim_states["active"] = time.time()
    logger.info("UI startup complete. (Multi-Modbus Monitor Mode)")


async def shutdown() -> None:
    global modbus_service
    if modbus_service:
        await modbus_service.stop()
        modbus_service = None


app.on_startup(startup)
app.on_shutdown(shutdown)

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(port=8888, dark=True, title="ESA Multi-Simulator Dashboard")
