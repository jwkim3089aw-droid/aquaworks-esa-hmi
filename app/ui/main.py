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

# 🚀 [ADD] 시스템 자원 모니터링 워커 임포트
from app.workers.sys_monitor import run_sys_monitor

# AI 상태 표시용
from app.workers.ai_state import get_ai_state

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

    devices = load_device_configs()
    current_rtu = {"id": 0}

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

    unit_map = {
        "do": "mg/L",
        "mlss": "mg/L",
        "temp": "°C",
        "ph": "",
        "air_flow": "m³/h",
        "power": "kW",
        "energy": "kWh",
    }

    def handle_rtu_change(new_id: int):
        current_rtu["id"] = new_id
        update_auto_ui()
        _tick_cards()
        if new_id == 0:
            ui.notify(
                "통합 관제 센터(Overview)로 이동합니다.", type="info", position="top", timeout=2.0
            )
        else:
            ui.notify(
                f"기계 #{new_id} 상세 뷰로 전환되었습니다.",
                type="positive",
                position="top",
                timeout=2.0,
            )

    create_header(current_rtu=current_rtu, on_rtu_change=handle_rtu_change)

    with ui.dialog() as ai_dialog:
        with ui.card().style(
            "min-width: 800px; background-color: #121212; border: 1px solid #333;"
        ):
            with ui.row().classes("w-full justify-between items-center mb-2"):
                ui.label("System Internals").classes("text-gray-400 font-bold")
                ui.button(icon="close", on_click=ai_dialog.close).props("flat round color=white")
            create_ai_panel(current_rtu=current_rtu)

    # =====================================================================
    # 🌟 뷰 1: 통합 관제 대시보드 (Overview) - 🚀 갯수 기반 동적 그리드 엔진
    # =====================================================================
    overview_refs: Dict[int, Dict[str, Any]] = {}

    num_devices = len(devices)
    if num_devices == 1:
        grid_css = "grid-cols-1 max-w-[600px]"
    elif num_devices == 2:
        grid_css = "grid-cols-1 xl:grid-cols-2 max-w-[1200px]"
    elif num_devices <= 4:
        grid_css = (
            f"grid-cols-1 lg:grid-cols-2 xl:grid-cols-{num_devices} max-w-[{500 * num_devices}px]"
        )
    elif num_devices <= 6:
        grid_css = "grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 max-w-[1500px]"
    elif num_devices <= 8:
        grid_css = "grid-cols-1 lg:grid-cols-3 xl:grid-cols-4 max-w-[2000px]"
    else:
        grid_css = "grid-cols-1 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 max-w-[2560px]"

    overview_container = ui.element("div").classes(
        f"w-full mx-auto px-4 grid gap-3 pb-6 mt-4 {grid_css} justify-center place-content-center"
    )
    overview_container.bind_visibility_from(current_rtu, "id", backward=lambda id: id == 0)

    with overview_container:
        for d in devices:
            r_id = d["id"]
            r_name = d.get("name", f"Machine {r_id}")
            overview_refs[r_id] = {}

            with (
                ui.card()
                .classes(
                    "bg-[#1e293b] rounded-xl border-t-2 border-t-cyan-500 shadow-xl cursor-pointer hover:bg-[#233044] transition-all hover:-translate-y-1 relative overflow-hidden p-0 flex flex-col"
                )
                .on("click", lambda e, id=r_id: handle_rtu_change(id))
            ):
                with ui.row().classes(
                    "w-full justify-between items-center px-4 py-2 bg-slate-800/40 border-b border-slate-700/50"
                ):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("circle", color="green-400", size="8px").classes(
                            "animate-pulse shadow-[0_0_8px_rgba(74,222,128,0.8)]"
                        )
                        ui.label(r_name).classes("text-lg font-bold text-white tracking-wide")

                    def toggle_ai(e, rtu_id=r_id):
                        state = get_sys_state(rtu_id)
                        state.auto_mode = not state.auto_mode
                        ui.notify(
                            (
                                f"🟢 기계 #{rtu_id} AI 제어 시작"
                                if state.auto_mode
                                else f"🔴 기계 #{rtu_id} AI 제어 중지"
                            ),
                            position="top",
                            timeout=2.0,
                        )
                        _tick_cards()

                    ai_btn = (
                        ui.button("MANUAL")
                        .classes("text-[9px] font-bold px-2 py-1 rounded cursor-pointer shadow-md")
                        .props("unelevated dense color=grey-8")
                        .on("click.stop", toggle_ai)
                    )
                    overview_refs[r_id]["ai_btn"] = ai_btn

                with ui.grid(columns=3).classes("w-full gap-2 p-3 flex-grow"):
                    for m in metrics:
                        m_key = str(m.get("key", title_of(m)))
                        if m_key in ["pump_hz", "valve_pos"]:
                            continue

                        m_title = str(m.get("title", m_key)).upper()
                        m_unit = unit_map.get(m_key.lower(), "")

                        with ui.column().classes(
                            "bg-slate-900/40 rounded-lg py-2 px-1 w-full shadow-inner border border-slate-700/30 flex flex-col items-center justify-center"
                        ):
                            ui.label(m_title).classes(
                                "text-[9px] text-slate-400 font-semibold tracking-wider leading-none mb-1 w-full text-center truncate"
                            )

                            with ui.row().classes(
                                "items-baseline gap-1 flex-nowrap justify-center w-full"
                            ):
                                txt_color = (
                                    "text-yellow-400"
                                    if "ph" in m_key.lower()
                                    else (
                                        "text-cyan-400"
                                        if "do" in m_key.lower()
                                        else "text-gray-100"
                                    )
                                )
                                lbl_val = ui.label("--").classes(
                                    f"text-xl font-mono {txt_color} font-bold leading-none"
                                )
                                overview_refs[r_id][m_key] = lbl_val

                                if m_unit:
                                    ui.label(m_unit).classes(
                                        "text-[8px] text-slate-500 font-bold whitespace-nowrap"
                                    )

                with ui.row().classes(
                    "w-full px-4 py-2 items-center justify-between border-t border-slate-700/50 bg-slate-800/30"
                ):
                    ui.label("TARGET DO").classes(
                        "text-[9px] text-slate-400 font-bold tracking-widest whitespace-nowrap"
                    )

                    def update_target_do(rtu_id, delta):
                        state = get_sys_state(rtu_id)
                        current_target = getattr(state, "target_do", 2.0)
                        new_target = round(max(0.0, min(10.0, current_target + delta)), 1)
                        state.target_do = new_target
                        state.auto_mode = True
                        overview_refs[rtu_id]["target_do"].set_text(f"{new_target:.1f}")
                        ui.notify(
                            f"🚀 AI 가동: {new_target:.1f}",
                            type="positive",
                            position="top",
                            timeout=1.0,
                        )
                        _tick_cards()

                    with ui.row().classes("items-center gap-1 flex-nowrap"):
                        ui.button(icon="remove").props("dense flat round size=xs").classes(
                            "text-slate-400 hover:text-white"
                        ).on("click.stop", lambda e, r=r_id: update_target_do(r, -0.1))

                        init_target = getattr(get_sys_state(r_id), "target_do", 2.0)

                        with ui.row().classes("items-baseline gap-1 flex-nowrap justify-center"):
                            lbl_target = ui.label(f"{init_target:.1f}").classes(
                                "text-lg font-mono text-cyan-300 font-bold w-8 text-right"
                            )
                            overview_refs[r_id]["target_do"] = lbl_target
                            ui.label("mg/L").classes(
                                "text-[8px] text-slate-500 font-bold whitespace-nowrap"
                            )

                        ui.button(icon="add").props("dense flat round size=xs").classes(
                            "text-slate-400 hover:text-white"
                        ).on("click.stop", lambda e, r=r_id: update_target_do(r, 0.1))

                with ui.row().classes(
                    "w-full bg-[#0b1120] p-3 px-4 flex-nowrap items-center justify-between"
                ):
                    with ui.column().classes("items-start"):
                        ui.label("PUMP").classes(
                            "text-[9px] text-slate-500 font-bold tracking-widest"
                        )
                        with ui.row().classes("items-baseline gap-1 flex-nowrap"):
                            lbl_pump = ui.label("--").classes(
                                "text-2xl font-mono text-white font-bold"
                            )
                            ui.label("Hz").classes(
                                "text-[9px] text-slate-600 font-bold whitespace-nowrap"
                            )
                        overview_refs[r_id]["pump_hz"] = lbl_pump

                    with ui.column().classes("items-end"):
                        ui.label("VALVE").classes(
                            "text-[9px] text-slate-500 font-bold tracking-widest"
                        )
                        with ui.row().classes("items-baseline gap-1 flex-nowrap"):
                            lbl_valve = ui.label("--").classes(
                                "text-2xl font-mono text-green-400 font-bold"
                            )
                            ui.label("%").classes(
                                "text-[9px] text-slate-600 font-bold whitespace-nowrap"
                            )
                        overview_refs[r_id]["valve_pos"] = lbl_valve

    # =====================================================================
    # 🌟 뷰 2: 개별 상세 뷰 (Detail)
    # =====================================================================
    detail_container = ui.element("div").classes(
        "w-full max-w-[1600px] mx-auto px-6 grid gap-3 grid-cols-1 xl:grid-cols-[215px_minmax(0,1fr)] mt-4 pb-10"
    )
    detail_container.bind_visibility_from(current_rtu, "id", backward=lambda id: id != 0)

    with detail_container:
        _, card_map = create_kpi_section(
            metrics, active_keys, on_selection_change=lambda: asyncio.create_task(_tick_trend())
        )

        with ui.element("div").classes("min-w-0 flex flex-col gap-3"):
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
            return

        state = get_sys_state(current_rtu["id"])

        for el in lock_targets:
            if state.auto_mode:
                el.disable()
            else:
                el.enable()

        if do_auto_btn:
            do_auto_btn.enable()
            do_auto_btn.props(remove="icon")
            if state.auto_mode:
                do_auto_btn.props("color=red")
                do_auto_btn.text = "STOP AUTO"
            else:
                do_auto_btn.props("color=primary")
                do_auto_btn.text = "START AUTO"

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
        if (
            val_list
            and isinstance(val_list[-1], (int, float))
            and not math.isnan(float(val_list[-1]))
        ):
            return fmt.format(float(val_list[-1]))
        return "--"

    def _tick_cards() -> None:
        if current_rtu["id"] == 0:
            for d in devices:
                r_id = d["id"]
                refs = overview_refs.get(r_id)
                if not refs:
                    continue

                _, data = get_last(r_id, 1)
                sys_state = get_sys_state(r_id)

                for m in metrics:
                    m_key = str(m.get("key", title_of(m)))
                    if m_key in refs:
                        fmt = "{:.1f}" if m_key in ("mlss", "air_flow", "do") else "{:.2f}"
                        refs[m_key].text = _safe_format(data.get(m_key, []), fmt)

                if "pump_hz" in refs:
                    refs["pump_hz"].text = _safe_format(data.get("pump_hz", []), "{:.1f}")
                if "valve_pos" in refs:
                    refs["valve_pos"].text = _safe_format(data.get("valve_pos", []), "{:.0f}")

                if sys_state.auto_mode:
                    refs["ai_btn"].text = "AI AUTO"
                    refs["ai_btn"].props("color=green-7 text-color=white")
                else:
                    refs["ai_btn"].text = "MANUAL"
                    refs["ai_btn"].props("color=grey-8 text-color=grey-4")

                if "target_do" in refs:
                    current_target = getattr(sys_state, "target_do", 2.0)
                    refs["target_do"].set_text(f"{current_target:.1f}")
            return

        _, data = get_last(current_rtu["id"], 180)
        for k, (_, v_label, _) in card_map.items():
            fmt = "{:.1f}" if k in ("mlss", "air_flow", "pump_hz", "do") else "{:.2f}"
            v_label.text = _safe_format(data.get(k, []), fmt)

        if lbl_cur_do:
            lbl_cur_do.text = _safe_format(data.get("do", []), "{:.2f}")
        if lbl_cur_valve:
            lbl_cur_valve.text = _safe_format(data.get("valve_pos", []), "{:.0f}")
        if lbl_cur_hz:
            lbl_cur_hz.text = _safe_format(data.get("pump_hz", []), "{:.1f}")

    ui.timer(1.0, lambda: asyncio.create_task(_tick_trend()))
    ui.timer(1.0, _tick_cards)

    clock_label = ui.label().classes("absolute top-2 right-4 text-[#9CA3AF] text-xs font-mono")
    ui.timer(1.0, lambda: clock_label.set_text(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


# ---------------------------------------------------------------------------
# Background Tasks & Lifecycle
# ---------------------------------------------------------------------------
_tasks: List[asyncio.Task[None]] = []


async def on_startup() -> None:
    log.info("[UI] Startup Sequence...")

    # 🚀 [PATCH] 버스 라우터 실행
    _tasks.append(asyncio.create_task(bus_router()))

    # 🚀 [PATCH] 시스템 자원 모니터링 태스크 백그라운드 등록 (.logs/sys_resources/ CSV 생성)
    _tasks.append(asyncio.create_task(run_sys_monitor()))
    log.info("[UI] System Monitor Started.")

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
        "title": "ESA Multi-Control Center",
        "host": host,
        "port": port,
        "reload": dev,
        "fastapi_docs": False,
        "show": os.getenv("NICEGUI_SHOW", "0") == "1",
        "endpoint_documentation": "none",
        "uvicorn_logging_level": "warning",
    }

    if dev:
        # 🚀 [PATCH] 파일 쓰기 시 무한 재시작 방지를 위해 .logs와 .data 경로 제외 추가
        run_kwargs["reload_excludes"] = [
            "logs/*",
            "*.log",
            "*.db",
            "*.db-journal",
            "__pycache__",
            ".data/*",  # AI 모델 및 설정 파일 저장소
            ".logs/*",  # 시스템 모니터링 CSV 등 신규 로깅 아키텍처 폴더
        ]

    NG_UI.run(**run_kwargs)
