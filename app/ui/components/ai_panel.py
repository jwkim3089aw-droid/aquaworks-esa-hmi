# app/ui/components/ai_panel.py
from __future__ import annotations
from nicegui import ui
import time
from typing import List, Dict, Any, Optional

# 🚀 전역 ai_state 대신 다중 장비를 지원하는 get_ai_state 임포트
from app.workers.ai_state import get_ai_state


def create_ai_panel(current_rtu: Optional[Dict[str, int]] = None) -> None:
    # 방어 코드: current_rtu가 넘어오지 않았을 경우 기본값
    if current_rtu is None:
        current_rtu = {"id": 1}

    CARD_STYLE = "background-color: #1e1e1e; border: 1px solid #333; border-radius: 8px;"
    LABEL_STYLE = "font-size: 0.75rem; color: #9ca3af; font-weight: bold;"
    VALUE_STYLE = "font-family: monospace; font-size: 1.05rem; color: #e5e7eb;"

    last_seq = -1
    last_q_seq = -1
    last_rtu_id = -1  # 🚀 기계 전환 감지용 변수
    cache = {}

    with ui.card().style(CARD_STYLE).classes("w-full p-4 gap-3"):
        # Header
        with ui.row().classes("w-full items-center justify-between"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("psychology", color="primary").classes("text-2xl")
                # 🚀 기계가 바뀔 때마다 텍스트가 업데이트될 타이틀 라벨
                title_lbl = ui.label("IMMORTAL AI KERNEL").classes("font-bold text-gray-200")

            with ui.row().classes("items-center gap-2"):
                status_chip = ui.chip("INIT").classes("font-bold")
                save_indicator = ui.spinner("dots", size="20px")
                save_indicator.set_visibility(False)

        err_lbl = ui.label("").classes("text-xs text-red-300")
        err_lbl.set_visibility(False)

        # Stats
        with ui.grid(columns=5).classes("w-full gap-2"):

            def stat_item(title: str):
                with ui.column().classes("bg-black/20 p-2 rounded items-center"):
                    ui.label(title).style(LABEL_STYLE)
                    return ui.label("--").style(VALUE_STYLE)

            v_eps = stat_item("EPSILON")
            v_loss = stat_item("LOSS")
            v_rew = stat_item("REWARD")
            v_steps = stat_item("STEPS")
            v_mem = stat_item("MEM")

        ui.separator().classes("bg-gray-700 my-1")

        # Chart Section
        with ui.row().classes("w-full items-center gap-4"):
            with ui.column().classes("items-center min-w-[110px]"):
                ui.label("CURRENT Hz").style(LABEL_STYLE)
                hz_lbl = ui.label("--").classes("text-2xl text-primary font-bold font-mono")
                delta_lbl = ui.label("(--)").classes("text-xs text-gray-400")

            chart = ui.echart(
                {
                    "grid": {"top": 5, "bottom": 20, "left": 5, "right": 5},
                    "xAxis": {
                        "type": "category",
                        "data": [],
                        "axisLabel": {"fontSize": 9, "color": "#666"},
                    },
                    "yAxis": {"show": False},
                    "series": [{"type": "bar", "data": []}],
                    "animationDuration": 200,
                }
            ).classes("h-24 flex-grow")

        # Footer Obs
        with ui.row().classes("w-full gap-4 text-xs text-gray-400 justify-end"):
            obs_lbl = ui.label("initializing...")

        # --- Helper ---
        def _fmt(v, fmt="{:.4f}"):
            if v is None:
                return "--"
            try:
                return fmt.format(v)
            except:
                return str(v)

        def _apply_status(running: bool, fatal: bool, train_mode: bool, hb_age: float):
            is_stale = hb_age > 3.0
            if fatal:
                status_chip.text = "FATAL"
                status_chip.props("color=red icon=error")
            elif running:
                if is_stale:
                    status_chip.text = "STALE"
                    status_chip.props("color=orange icon=warning")
                elif train_mode:
                    status_chip.text = "TRAINING"
                    status_chip.props("color=green icon=school")
                else:
                    status_chip.text = "INFERENCE"
                    status_chip.props("color=blue icon=visibility")
            else:
                status_chip.text = "STOPPED"
                status_chip.props("color=grey icon=stop")

        # --- Update Logic ---
        def update_ui():
            nonlocal last_seq, last_q_seq, cache, last_rtu_id
            try:
                # 🚀 핵심: 현재 선택된 기계 ID를 가져오고, 해당 기계의 AI 상태를 불러옵니다.
                rtu_id = current_rtu["id"]
                current_ai_state = get_ai_state(rtu_id)

                # 🚀 기계 전환이 감지되면 화면의 데이터를 강제로 초기화하고 렌더링 시퀀스를 리셋합니다.
                if rtu_id != last_rtu_id:
                    title_lbl.text = f"IMMORTAL AI KERNEL [Machine #{rtu_id}]"
                    last_seq = -1
                    last_q_seq = -1
                    cache = {}
                    last_rtu_id = rtu_id

                # 1. 메타 데이터 읽기 (항상 수행 -> Heartbeat 반응성 보장)
                seq, q_seq, hb_ts, running, fatal, last_error, save_inflight, train_mode = (
                    current_ai_state.peek_meta()
                )

                now = time.monotonic()
                hb_age = (now - hb_ts) if hb_ts > 0 else 9999.0

                _apply_status(running, fatal, train_mode, hb_age)
                save_indicator.set_visibility(bool(save_inflight))

                if last_error:
                    err_lbl.text = f"ERR: {last_error}"
                    err_lbl.set_visibility(True)
                else:
                    err_lbl.set_visibility(False)

                obs_lbl.text = (
                    f"TgtDO: {_fmt(cache.get('target_do'), '{:.2f}')} | "
                    f"CurDO: {_fmt(cache.get('do_filt'), '{:.2f}')} | "
                    f"Temp: {_fmt(cache.get('temp_filt'), '{:.1f}')} | "
                    f"Ping: {hb_age:.1f}s"
                )

                # 2. 전체 데이터 갱신 (Seq 변경 시에만 수행 -> 무거운 작업 최소화)
                if seq != last_seq:
                    new_seq, _, st = current_ai_state.snapshot_if_changed(
                        last_seq, max_state_vector=64
                    )

                    if st:
                        last_seq = new_seq
                        cache = st

                        v_eps.text = _fmt(cache.get("epsilon"), "{:.1%}")
                        v_loss.text = _fmt(cache.get("last_loss"), "{:.5f}")
                        v_rew.text = _fmt(cache.get("last_reward"), "{:+.2f}")
                        v_steps.text = _fmt(cache.get("steps_done"), "{:,}")
                        v_mem.text = _fmt(cache.get("memory_len"), "{:,}")

                        hz = cache.get("current_hz")
                        delta = cache.get("last_action_delta")
                        if hz is not None:
                            hz_lbl.text = f"{float(hz):.1f}"
                        if delta is not None:
                            d = float(delta)
                            delta_lbl.text = f"({d:+.1f} Hz)"
                            delta_lbl.classes(
                                (
                                    "text-red-400"
                                    if d < 0
                                    else "text-green-400" if d > 0 else "text-gray-400"
                                ),
                                remove="text-red-400 text-green-400 text-gray-400",
                            )

                # 3. 차트 갱신 (Q-Seq 변경 시에만 수행 -> 렌더링 부하 최소화)
                if q_seq != last_q_seq:
                    last_q_seq = q_seq
                    q_vals = cache.get("q_values") or []
                    action_map = cache.get("action_map") or []

                    if q_vals:
                        if action_map and len(action_map) == len(q_vals):
                            chart.options["xAxis"]["data"] = [
                                f"{float(a):+.1f}" for a in action_map
                            ]
                        else:
                            chart.options["xAxis"]["data"] = [str(i) for i in range(len(q_vals))]

                        max_idx = 0
                        max_v = None
                        for i, v in enumerate(q_vals):
                            try:
                                fv = float(v)
                            except:
                                continue
                            if max_v is None or fv > max_v:
                                max_v = fv
                                max_idx = i

                        series_data: List[Dict[str, Any]] = []

                        for i, v in enumerate(q_vals):
                            item: Dict[str, Any] = {"value": float(v)}

                            if i == max_idx:
                                if action_map and len(action_map) == len(q_vals):
                                    a = float(action_map[i])
                                    item["itemStyle"] = {
                                        "color": (
                                            "#22c55e"
                                            if a > 0
                                            else "#ef4444" if a < 0 else "#3b82f6"
                                        )
                                    }
                                else:
                                    item["itemStyle"] = {"color": "#3b82f6"}
                            else:
                                item["itemStyle"] = {"color": "#334155"}
                            series_data.append(item)

                        chart.options["series"][0]["data"] = series_data
                        chart.update()

            except Exception as e:
                err_lbl.text = f"UI UPDATE ERROR: {e}"
                err_lbl.set_visibility(True)

        ui.timer(0.5, update_ui)
