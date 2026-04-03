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
    if current_rtu is None:
        current_rtu = {"id": 1}

    def clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(v)))

    def value_as_float(num: Any, default: float = 0.0) -> float:
        v = getattr(num, "value", None)
        return float(v) if isinstance(v, (int, float)) else default

    def pm_text(char: str, on_click: Callable[[], None]) -> Any:
        el = ui.label(char).classes(
            "pm-txt text-lg px-2 cursor-pointer hover:text-white text-gray-400 select-none"
        )
        el.on("click.stop", lambda _e: on_click())
        return el

    def number_box(
        value: float,
        lo: float,
        hi: float,
        step: float = 1.0,
        fmt: str = "%.0f",
        on_change: Callable[[float], None] = None,
    ) -> Any:
        num = (
            ui.number(value=value, min=lo, max=hi, step=step, format=fmt)
            .props(
                'outlined dense input-style="text-align: center; color: white; font-size: 13px;"'
            )
            .classes("w-[75px]")
        )

        if on_change:
            num.on("update:model-value", lambda e: on_change(float(e.args)) if e.args else None)

        def dec():
            new_val = clamp(value_as_float(num, value) - step, lo, hi)
            new_val = round(new_val, 1) if step < 1.0 else int(round(new_val))
            num.set_value(new_val)
            if on_change:
                on_change(new_val)

        def inc():
            new_val = clamp(value_as_float(num, value) + step, lo, hi)
            new_val = round(new_val, 1) if step < 1.0 else int(round(new_val))
            num.set_value(new_val)
            if on_change:
                on_change(new_val)

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
            ui.button("APPLY", color="teal-6")
            .props("unelevated dense size=sm")
            .classes("px-2 min-h-[24px] font-bold text-[11px]")
            .on("click.stop", _on_click)
        )

    cmd_card = ui.card().classes(
        "cmds w-full h-[260px] min-w-0 overflow-hidden bg-[#0F172A] rounded-xl shadow-lg border border-[#1F2937] flex flex-col p-0 gap-0"
    )

    lbl_cur_do = lbl_cur_valve = lbl_cur_hz = None
    lbl_set_do = lbl_set_valve = lbl_set_hz = None
    do_auto_btn = ai_btn = None
    do_num = None

    with cmd_card:
        with ui.row().classes(
            "w-full h-[30px] items-center px-3 bg-[#162032] border-b border-[#1F2937] justify-between"
        ):
            ui.label("Commands").classes("text-xs font-bold text-[#E5E7EB]")
            if on_ai_click:
                with (
                    ui.button(icon="psychology")
                    .props("flat round dense size=xs text-color=grey-7")
                    .on("click.stop", on_ai_click) as ai_btn
                ):
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
                lbl_set_do = ui.label(f"{init_state.target_do:.1f}").classes(
                    "text-sm text-cyan-400 font-mono font-bold"
                )

                def _on_do_change(val: float):
                    state = get_sys_state(current_rtu["id"])
                    state.target_do = val
                    sync_state["target_do"] = val
                    if lbl_set_do:
                        lbl_set_do.text = f"{val:.1f}"

                    # 🚀 [FIX] UI에서 값이 변경되면 백엔드 큐에 넣어 Manager가 알게 함
                    try:
                        asyncio.create_task(
                            command_q.put((current_rtu["id"], "target_do", float(val)))
                        )
                    except Exception as e:
                        log.warning(f"Target DO command failed: {val} ({e})")

                with ui.row().classes("justify-center"):
                    do_num = number_box(
                        init_state.target_do,
                        0.0,
                        10.0,
                        step=0.1,
                        fmt="%.1f",
                        on_change=_on_do_change,
                    )

                async def _toggle_auto_mode() -> None:
                    rtu_id = current_rtu["id"]
                    state = get_sys_state(rtu_id)
                    is_auto = not state.auto_mode

                    if not is_auto:
                        state.auto_mode = False
                        ui.notify(
                            f"🛑 [Machine #{rtu_id}] Auto Control STOPPED",
                            type="warning",
                            timeout=2.0,
                        )
                    else:
                        state.auto_mode = True
                        ui.notify(
                            f"🚀 [Machine #{rtu_id}] Auto Control STARTED",
                            type="positive",
                            timeout=2.0,
                        )

                    btn_any = cast(Any, do_auto_btn)
                    if btn_any and hasattr(btn_any, "_update_ui_callback"):
                        btn_any._update_ui_callback()

                with ui.row().classes("justify-center items-center gap-1 flex-nowrap"):
                    do_auto_btn = (
                        ui.button("START AUTO")
                        .props("unelevated dense size=sm color=primary icon=play_arrow")
                        .classes("px-4 min-h-[28px] text-[11px] font-bold")
                        .on("click.stop", _toggle_auto_mode)
                    )

            # 2. Valve Position
            with ui.element("div").classes(
                GRID_Template + " h-[40px] border-b border-[#1F2937]/50"
            ):
                ui.label("Valve (%)").classes("text-xs text-gray-400 font-bold text-left pl-1")
                lbl_cur_valve = ui.label("--").classes("text-sm text-green-400 font-mono font-bold")
                lbl_set_valve = ui.label("50").classes("text-sm text-cyan-400 font-mono font-bold")

                with ui.row().classes("justify-center"):
                    valve_num = number_box(50, 0, 100, step=5.0)
                    lock_targets.append(valve_num)

                with ui.row().classes("justify-center"):
                    async def _apply_valve(val: float) -> None:
                        rtu_id = current_rtu["id"]
                        try:
                            await command_q.put((rtu_id, "valve_pos", float(val)))
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
                    hz_num = number_box(40, 20, 60, step=1.0)
                    lock_targets.append(hz_num)

                with ui.row().classes("justify-center items-center gap-2"):
                    async def _apply_pump_hz(val: float) -> None:
                        rtu_id = current_rtu["id"]
                        try:
                            await command_q.put((rtu_id, "set_hz", float(val)))
                        except Exception as e:
                            log.warning(f"Pump Hz command failed: {val} ({e})")

                    h_btn = apply_btn(
                        lbl_set_hz, lambda: value_as_float(hz_num, 40.0), on_apply=_apply_pump_hz
                    )
                    lock_targets.append(h_btn)

    sync_state = {"last_rtu": current_rtu["id"], "target_do": init_state.target_do}

    def sync_controls():
        rtu_id = current_rtu["id"]
        if rtu_id == 0:
            return
        state = get_sys_state(rtu_id)

        if lbl_set_do:
            lbl_set_do.text = f"{state.target_do:.1f}"

        if sync_state["last_rtu"] != rtu_id:
            sync_state["last_rtu"] = rtu_id
            sync_state["target_do"] = state.target_do
            if do_num:
                do_num.set_value(state.target_do)
        elif sync_state["target_do"] != state.target_do:
            sync_state["target_do"] = state.target_do
            if do_num:
                do_num.set_value(state.target_do)

    ui.timer(1.0, sync_controls)

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
