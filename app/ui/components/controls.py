# app/ui/components/controls.py
import os
import asyncio
from typing import Any, Callable, List, Tuple, cast, Optional, Dict
from nicegui import ui

from app.stream.state import get_sys_state, command_q
from app.ui.common import log


def create_control_section(
    lock_targets: List[Any],
    on_ai_click: Optional[Callable[[], None]] = None,
    current_rtu: Optional[Dict[str, int]] = None,
) -> Tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    """
    Returns: (lbl_cur_do, lbl_cur_valve, lbl_cur_hz, do_auto_btn, lbl_set_do, lbl_set_valve, lbl_set_hz, ai_btn)
    """
    # 기본 방어 코드
    if current_rtu is None:
        current_rtu = {"id": 1}

    # --- Helper Functions ---
    def clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(v)))

    def value_as_float(num: Any, default: float = 0.0) -> float:
        v = getattr(num, "value", None)
        return float(v) if isinstance(v, (int, float)) else default

    def pm_text(char: str, on_click: Callable[[], None]) -> Any:
        el = ui.label(char).classes(
            "pm-txt text-lg px-2 cursor-pointer hover:text-white text-gray-400"
        )
        el.on("click", lambda _e: on_click())
        return el

    def number_box(value: float, lo: float, hi: float, step: float = 1.0) -> Any:
        num = (
            ui.number(value=value, min=lo, max=hi, step=step, format="%.0f")
            .props(
                'outlined dense input-style="text-align: center; color: white; font-size: 13px;"'
            )
            .classes("w-[75px]")
        )

        def dec():
            num.set_value(clamp(value_as_float(num, value) - step, lo, hi))

        def inc():
            num.set_value(clamp(value_as_float(num, value) + step, lo, hi))

        with num.add_slot("prepend"):
            pm_text("−", dec)
        with num.add_slot("append"):
            pm_text("+", inc)
        return num

    def apply_btn(
        label_sv: Any, get_val: Callable[[], float], on_apply: Callable[[float], Any] | None = None
    ) -> Any:
        async def _on_click(_: Any) -> None:
            val = get_val()
            label_sv.text = f"{val:.1f}" if "." in str(val) else f"{val:.0f}"
            if on_apply:
                try:
                    res = on_apply(val)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as e:
                    log.exception(f"apply error: {e}")

        return (
            ui.button("APPLY", color="primary")
            .props("unelevated dense size=md")
            .classes("px-3 min-h-[24px]")
            .on("click", _on_click)
        )

    # --- UI Construction ---
    cmd_card = ui.card().classes(
        "cmds w-full h-[260px] min-w-0 overflow-hidden bg-[#0F172A] rounded-xl shadow-lg border border-[#1F2937] flex flex-col p-0 gap-0"
    )

    lbl_cur_do = lbl_cur_valve = lbl_cur_hz = None
    lbl_set_do = lbl_set_valve = lbl_set_hz = None
    do_auto_btn = ai_btn = None

    with cmd_card:
        # Header 영역
        with ui.row().classes(
            "w-full h-[30px] items-center px-3 bg-[#162032] border-b border-[#1F2937] justify-between"
        ):
            ui.label("Commands").classes("text-xs font-bold text-[#E5E7EB]")

            if on_ai_click:
                with ui.button(icon="psychology", on_click=on_ai_click).props(
                    "flat round dense size=xs text-color=grey-7"
                ) as ai_btn:
                    ui.tooltip("AI Internal State")
            else:
                ai_btn = ui.element("div").classes("hidden")

        content_div = ui.element("div").classes(
            "w-full flex-1 flex flex-col justify-evenly px-4 py-2"
        )
        with content_div:
            GRID_Template = (
                "grid grid-cols-[5rem_4rem_4rem_5rem_auto] items-center gap-1 w-full text-center"
            )

            with ui.element("div").classes(
                GRID_Template + " text-[10px] text-gray-500 font-bold uppercase"
            ):
                for label in ["", "Current", "Set", "Control", "Action"]:
                    ui.label(label)

            init_state = get_sys_state(current_rtu["id"])

            # 1. Target DO
            with ui.element("div").classes(
                GRID_Template + " h-[40px] border-b border-[#1F2937]/50"
            ):
                ui.label("DO (mg/L)").classes("text-xs text-green-400 font-bold text-left pl-1")
                lbl_cur_do = ui.label("--").classes("text-sm text-green-400 font-mono font-bold")
                lbl_set_do = ui.label(f"{init_state.target_do}").classes(
                    "text-sm text-cyan-400 font-mono font-bold"
                )

                with ui.row().classes("justify-center"):
                    do_num = number_box(init_state.target_do, 0, 20.0, step=0.1)

                async def _toggle_auto_mode() -> None:
                    rtu_id = current_rtu["id"]
                    state = get_sys_state(rtu_id)
                    is_auto = not state.auto_mode

                    if not is_auto:
                        state.auto_mode = False
                        ui.notify(f"🛑 [Machine #{rtu_id}] Auto Control STOPPED", type="warning")
                    else:
                        val = value_as_float(do_num, 2.0)
                        state.target_do = float(val)
                        lbl_set_do.text = f"{val:.1f}"
                        state.auto_mode = True
                        ui.notify(
                            f"🚀 [Machine #{rtu_id}] Auto Control STARTED (Target: {val})",
                            type="positive",
                        )

                    btn_any = cast(Any, do_auto_btn)
                    if btn_any and hasattr(btn_any, "_update_ui_callback"):
                        btn_any._update_ui_callback()

                with ui.row().classes("justify-center gap-1"):
                    do_auto_btn = (
                        ui.button("START AUTO", on_click=_toggle_auto_mode)
                        .props("unelevated dense size=sm color=primary icon=play_arrow")
                        .classes("px-2 min-h-[24px]")
                    )

            # 2. Valve Position
            with ui.element("div").classes(
                GRID_Template + " h-[40px] border-b border-[#1F2937]/50"
            ):
                ui.label("Valve (%)").classes("text-xs text-gray-400 font-bold text-left pl-1")
                lbl_cur_valve = ui.label("--").classes("text-sm text-green-400 font-mono font-bold")
                lbl_set_valve = ui.label("50").classes("text-sm text-cyan-400 font-mono font-bold")

                with ui.row().classes("justify-center"):
                    valve_num = number_box(50, 0, 100, step=5)
                    lock_targets.append(valve_num)

                with ui.row().classes("justify-center"):

                    async def _apply_valve(val: float) -> None:
                        rtu_id = current_rtu["id"]
                        try:
                            await command_q.put((rtu_id, "valve_pos", float(val)))
                            log.info(f"✅ Command Sent: [RTU {rtu_id}] Valve -> {val}")

                            # 🚀 [핵심 패치] 시각적 피드백 강제 적용
                            # 밸브는 현재 피드백 센서가 없으므로, APPLY를 누르면 화면의 Current 값도 즉시 바꿔서 작동했음을 직관적으로 알림
                            if lbl_cur_valve:
                                lbl_cur_valve.text = f"{val:.0f}"

                        except Exception as e:
                            log.warning(f"Valve command failed: {val} ({e})")

                    v_btn = apply_btn(
                        lbl_set_valve,
                        lambda: value_as_float(valve_num, 50.0),
                        on_apply=_apply_valve,
                    )
                    lock_targets.append(v_btn)

            # 3. Pump Freq
            with ui.element("div").classes(GRID_Template + " h-[40px]"):
                ui.label("Pump (Hz)").classes("text-xs text-gray-400 font-bold text-left pl-1")
                lbl_cur_hz = ui.label("--").classes("text-sm text-green-400 font-mono font-bold")
                lbl_set_hz = ui.label("40").classes("text-sm text-cyan-400 font-mono font-bold")

                with ui.row().classes("justify-center"):
                    hz_num = number_box(40, 20, 60)
                    lock_targets.append(hz_num)

                with ui.row().classes("justify-center items-center gap-2"):

                    async def _apply_pump_hz(val: float) -> None:
                        rtu_id = current_rtu["id"]
                        try:
                            await command_q.put((rtu_id, "set_hz", float(val)))
                            log.info(f"✅ Command Sent: [RTU {rtu_id}] Pump Hz -> {val}")
                        except Exception as e:
                            log.warning(f"Pump Hz command failed: {val} ({e})")

                    h_btn = apply_btn(
                        lbl_set_hz, lambda: value_as_float(hz_num, 40.0), on_apply=_apply_pump_hz
                    )
                    lock_targets.append(h_btn)

    return (
        lbl_cur_do,
        lbl_cur_valve,
        lbl_cur_hz,
        do_auto_btn,
        lbl_set_do,
        lbl_set_valve,
        lbl_set_hz,
        ai_btn,
    )
