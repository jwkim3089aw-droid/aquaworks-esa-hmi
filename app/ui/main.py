# app/ui/main.py
# ESA_HMI UI — 메인 대시보드 (Multi-RTU Dynamic Scale-Out Ready)

from __future__ import annotations
import os
import asyncio
import logging
import math
import traceback
from datetime import datetime
from typing import Any, List, Dict, Set, Optional, cast, Sequence

# NiceGUI
from nicegui import ui, app as ng_app

# Internal Components & Config
from app.ui.settings import settings_page
from app.stream.state import get_sys_state, get_last, stop_bus, bus_router
from app.core.config import get_settings
from app.core.db import engine, Base
from app.ui.theme import apply_theme
from app.ui.config import METRICS
from app.core.device_config import load_device_configs

# UI Sections
from app.ui.common import log, APP_CSS, title_of
from app.ui.components.header import create_header
from app.ui.components.kpi import create_kpi_section
from app.ui.components.chart import create_chart_section
from app.ui.components.marks import create_marks_section
from app.ui.components.controls import create_control_section
from app.ui.components.ai_panel import create_ai_panel

# API & Background Tasks
from app.api import api_router
from app.api.v1.rtu_ops import router as rtu_ops_router
from app.api.v1.rtu_control import router as rtu_control_router
from app.api.v1.telemetry import simulator_task
from app.services.telemetry_store import get_store

# ---------------------------------------------------------------------------
# Logging & Setup
# ---------------------------------------------------------------------------
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("asyncua").setLevel(logging.WARNING)

NG_APP: Any = cast(Any, ng_app)
NG_UI: Any = cast(Any, ui)

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
NG_APP.add_static_files("/static", os.path.join(_project_root, "static"))


# ---------------------------------------------------------------------------
# Main Page
# ---------------------------------------------------------------------------
def page() -> None:
    apply_theme()
    ui.add_head_html('<meta http-equiv="Cache-Control" content="no-store, no-cache, max-age=0">')
    ui.add_head_html(APP_CSS)
    ui.add_css(
        ".history-card .q-table__container, .cmds .q-table__container{overflow-x:auto;} .history-card{min-width:0!important;}"
    )

    # 🚀 하드코딩 탈피: JSON에서 기기 ID 로드
    devices = load_device_configs()
    current_rtu = {"id": devices[0]["id"] if devices else 0}

    # Data & UI State Setup
    metrics: List[Dict[str, Any]] = cast(List[Dict[str, Any]], METRICS)
    active_keys: Set[str] = set()
    trend_marks: List[Dict[str, Any]] = []
    lock_targets: List[Any] = []

    base_palette = [
        "#5470C6",
        "#91CC75",
        "#EE6666",
        "#FAC858",
        "#73C0DE",
        "#3BA272",
        "#FC8452",
        "#9A60B4",
        "#EA7CCC",
    ]
    series_colors_by_key = {
        str(m.get("key", title_of(m))): base_palette[i % len(base_palette)]
        for i, m in enumerate(metrics)
    }
    metric_keys = list(series_colors_by_key.keys())

    # --- Header & AI Panel ---
    def handle_rtu_change(new_id: int):
        current_rtu["id"] = new_id
        update_auto_ui()
        _tick_cards()
        ui.notify(f"Dashboard Switched to Machine #{new_id}", type="info", position="top")

    create_header(current_rtu=current_rtu, on_rtu_change=handle_rtu_change)

    # 🐛 [픽스] 컨텍스트 매니저를 분리하여 더 안전하게 구성
    with ui.dialog() as ai_dialog:
        with ui.card().style(
            "min-width: 800px; background-color: #121212; border: 1px solid #333;"
        ):
            with ui.row().classes("w-full justify-between items-center mb-2"):
                ui.label("System Internals").classes("text-gray-400 font-bold")
                ui.button(icon="close", on_click=ai_dialog.close).props("flat round color=white")
            create_ai_panel(current_rtu=current_rtu)

    # --- Main Layout ---
    with ui.element("div").classes(
        "w-full max-w-[1400px] mx-auto px-6 grid gap-3 grid-cols-1 xl:grid-cols-[215px_minmax(0,1fr)] h-full"
    ):

        # 1. Left: KPI Cards
        _, card_map = create_kpi_section(
            metrics, active_keys, on_selection_change=lambda: _tick_trend()
        )

        # 2. Right: Trend & Commands
        with ui.element("div").classes("min-w-0 h-full flex flex-col gap-3"):
            with ui.row().classes("w-full items-start gap-3"):
                with ui.element("div").classes("flex-1 min-w-0 w-full"):
                    _trend_chart, _tick_trend_func = create_chart_section(
                        metrics,
                        active_keys,
                        series_colors_by_key,
                        on_chart_click=lambda e, xs, m: _handle_chart_click_logic(e, xs, m),
                        current_rtu=current_rtu,
                    )

            with ui.row().classes("w-full gap-3 items-start flex-wrap xl:flex-nowrap flex-none"):
                with ui.element("div").classes("basis-full xl:basis-3/5 min-w-0 max-w-full"):
                    render_trend_marks = create_marks_section(
                        trend_marks, metrics, metric_keys, series_colors_by_key
                    )

                with ui.element("div").classes(
                    "basis-full xl:basis-2/5 min-w-0 max-w-full flex flex-col gap-3"
                ):
                    (
                        lbl_cur_do,
                        lbl_cur_valve,
                        lbl_cur_hz,
                        do_auto_btn,
                        lbl_set_do,
                        _,
                        _,
                        ai_btn,
                    ) = create_control_section(
                        lock_targets, on_ai_click=ai_dialog.open, current_rtu=current_rtu
                    )

    # --- Logic Integration ---
    def update_auto_ui() -> None:
        if current_rtu["id"] == 0:
            for el in lock_targets:
                el.disable()
            if do_auto_btn:
                do_auto_btn.disable()
            if ai_btn:
                ai_btn.disable()
            return

        state = get_sys_state(current_rtu["id"])

        # 🐛 [픽스] 체이닝 제거 및 명시적 제어
        for el in lock_targets:
            if state.auto_mode:
                el.disable()
            else:
                el.enable()

        if do_auto_btn:
            do_auto_btn.enable()
            if state.auto_mode:
                do_auto_btn.props("color=red icon=stop")
                do_auto_btn.text = "STOP"
            else:
                do_auto_btn.props("color=primary icon=play_arrow")
                do_auto_btn.text = "APPLY"

        if ai_btn:
            if state.auto_mode:
                ai_btn.enable()
                ai_btn.props("text-color=green-4")
            else:
                ai_btn.disable()
                ai_btn.props("text-color=grey-9")

    if do_auto_btn:
        do_auto_btn._update_ui_callback = update_auto_ui

    update_auto_ui()
    render_trend_marks()

    def _handle_chart_click_logic(e: Any, xs_eff: List[str], m_eff: int):
        if current_rtu["id"] == 0:
            return

        idx = getattr(e, "dataIndex", getattr(e, "data_index", None))
        if idx is None and hasattr(e, "args") and isinstance(e.args, dict):
            idx = e.args.get("dataIndex")

        if idx is None or idx < 0 or idx >= m_eff:
            return

        ts_label = xs_eff[idx]
        if trend_marks and trend_marks[-1]["ts_label"] == ts_label:
            return

        full_xs, full_data = get_last(current_rtu["id"], 3600)
        try:
            real_idx = list(full_xs).index(ts_label)
        except ValueError:
            return

        mark_values = {}
        for key in metric_keys:
            series_raw = list(cast(Sequence[Any], full_data.get(key, ())))
            val = (
                float(series_raw[real_idx])
                if real_idx < len(series_raw) and isinstance(series_raw[real_idx], (int, float))
                else None
            )
            mark_values[key] = None if val is not None and math.isnan(val) else val

        if any(v is not None for v in mark_values.values()):
            trend_marks.append({"ts_label": ts_label, "values": mark_values})
            render_trend_marks()
            _trend_chart.run_chart_method(
                "dispatchAction", {"type": "showTip", "seriesIndex": 0, "dataIndex": idx}
            )

    async def _tick_trend():
        if current_rtu["id"] != 0:
            await _tick_trend_func()

    def _safe_format(val_list: Sequence[Any], fmt: str) -> str:
        """안전한 데이터 포매팅 헬퍼 함수"""
        if (
            val_list
            and isinstance(val_list[-1], (int, float))
            and not math.isnan(float(val_list[-1]))
        ):
            return fmt.format(float(val_list[-1]))
        return "--"

    def _tick_cards() -> None:
        if current_rtu["id"] == 0:
            for _, (_, v_label, _) in card_map.items():
                v_label.text = "--"
            for lbl in [lbl_cur_do, lbl_cur_valve, lbl_cur_hz]:
                if lbl:
                    lbl.text = "--"
            return

        _, data = get_last(current_rtu["id"], 180)

        # 1. KPI 카드 업데이트
        for k, (_, v_label, _) in card_map.items():
            fmt = "{:.1f}" if k in ("mlss", "air_flow", "pump_hz", "do") else "{:.2f}"
            v_label.text = _safe_format(data.get(k, []), fmt)

        # 2. Control 패널 현재값 업데이트
        if lbl_cur_do:
            lbl_cur_do.text = _safe_format(data.get("do", []), "{:.2f}")
        if lbl_cur_valve:
            lbl_cur_valve.text = _safe_format(data.get("valve_pos", []), "{:.0f}")
        if lbl_cur_hz:
            lbl_cur_hz.text = _safe_format(data.get("pump_hz", []), "{:.1f}")

    # 타이머 등록
    ui.timer(1.0, _tick_trend)
    ui.timer(2.0, _tick_cards)

    clock_label = ui.label().classes("absolute top-2 right-4 text-[#9CA3AF] text-xs")
    ui.timer(1.0, lambda: clock_label.set_text(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


# ---------------------------------------------------------------------------
# Background Tasks & Lifecycle
# ---------------------------------------------------------------------------
_tasks: List[asyncio.Task[None]] = []


async def on_startup() -> None:
    log.info("[UI] Startup Sequence...")
    _tasks.append(asyncio.create_task(bus_router()))

    try:
        s = get_settings()
        if getattr(s, "ENABLE_SIMULATION", True):
            _tasks.append(
                asyncio.create_task(
                    simulator_task(get_store(), getattr(s, "SIM_INTERVAL_SEC", 1.0))
                )
            )
            log.info("[UI] Simulator Started.")
    except Exception as e:
        log.warning(f"[UI] Simulator Init Failed: {e}")

    try:
        import app.models.settings
        import app.models

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        log.error(f"[UI] DB Init Failed: {e}")

    from app.workers.manager import manager

    try:
        await manager.initialize()
        log.info("[UI] Manager Initialized.")
    except Exception as e:
        log.error(f"[UI] Manager Start Failed: {e}")


async def on_shutdown() -> None:
    log.info("[UI] Shutdown Sequence...")
    stop_bus()
    for t in _tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


@ui.page("/settings")
async def route_settings():
    try:
        apply_theme()
        await settings_page()
    except Exception:
        err_msg = traceback.format_exc()
        log.error(f"Settings Page Error: {err_msg}")
        apply_theme()
        with ui.column().classes("w-full p-10"):
            ui.label("Settings Page Error!").classes("text-3xl text-red-500 font-bold")
            ui.code(err_msg).classes("w-full bg-slate-900 text-red-300 p-4 rounded")
            ui.button("Go Back", on_click=lambda: ui.navigate.to("/")).classes("mt-4")


if __name__ in {"__main__", "__mp_main__"}:
    NG_UI.page("/")(page)
    NG_APP.on_startup(on_startup)
    NG_APP.on_shutdown(on_shutdown)

    NG_APP.include_router(api_router)
    NG_APP.include_router(rtu_ops_router)
    NG_APP.include_router(rtu_control_router)

    S = get_settings()
    host = os.getenv("NICEGUI_HOST", os.getenv("ESA_UI_HOST", S.UI_HOST))
    port = int(os.getenv("NICEGUI_PORT", os.getenv("ESA_UI_PORT", str(S.UI_PORT))))
    dev = os.getenv("ESA_DEV") == "1"

    run_kwargs = {
        "title": "ESA_HMI",
        "host": host,
        "port": port,
        "reload": dev,
        "fastapi_docs": False,
        "show": os.getenv("NICEGUI_SHOW", "0") == "1",
        "endpoint_documentation": "none",
        "uvicorn_logging_level": "warning",
    }
    if dev:
        run_kwargs["reload_excludes"] = ["logs/*", "*.log", "*.db", "*.db-journal", "__pycache__"]

    NG_UI.run(**run_kwargs)
