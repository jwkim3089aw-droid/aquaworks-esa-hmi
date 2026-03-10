# app/ui/commands.py
from __future__ import annotations

import logging
from typing import Callable, Any, Tuple

from nicegui import ui

from app.stream.state import command_q

# 서비스(stdout)에서도 무조건 보이게 하려고 print도 같이 씁니다.
logger = logging.getLogger("esa_hmi.ui")
logger.info("[COMMANDS] module loaded")
print("[COMMANDS] module loaded")  # -> nssm의 service_stdout.log로 들어감

NumberGetter = Callable[[], float]


# 🎯 [핵심 패치] step과 format을 변수로 받아서 소수점과 정수를 모두 소화할 수 있게 만듦!
def _number_box(
    value: float, lo: float, hi: float, step_val: float = 1.0, fmt: str = "%.0f"
) -> Any:
    return (
        ui.number(value=value, min=lo, max=hi, step=step_val, format=fmt)
        .props("outlined dense input-class=text-center")
        .classes("w-[88px]")
    )


def _pm_text(char: str, on_click: Callable[[], None]) -> Any:
    el = ui.label(char).classes("pm-txt cursor-pointer hover:text-white transition-colors")
    el.on("click", lambda _e: on_click())
    return el


def _plus_minus(on_minus: Callable[[], None], on_plus: Callable[[], None]) -> Tuple[Any, Any]:
    return _pm_text("−", on_minus), _pm_text("+", on_plus)


def _apply_btn(label_txt: str, key: str, get_val: NumberGetter) -> Any:
    async def send(_e=None):
        try:
            val = float(get_val() or 0.0)
            await command_q.put((key, val))

            # ✅ “큐에 들어갔다”를 로그/print로 확실히 남김
            logger.info(f"[CMD_ENQ] {key}={val}")
            print(f"[CMD_ENQ] {key}={val}")

            ui.notify(f"Sent: {key} = {val}", type="positive", position="bottom", timeout=2.0)
        except Exception as e:
            logger.exception(f"[CMD_ENQ_ERR] key={key} err={e}")
            print(f"[CMD_ENQ_ERR] key={key} err={e}")
            ui.notify(f"Command send error: {e}", type="negative", position="bottom")

    return (
        ui.button(label_txt, icon="check", color="primary")
        .props("unelevated dense")
        .on("click", send)
    )


# 오토 스위치는 UI 표시용 (명령 전송 X)
def _auto_switch() -> Any:
    sw = ui.switch("AUTO OFF").props('dense color="green" keep-color')
    sw.classes("text-xs text-[#9CA3AF] font-bold")

    def _update(e):
        is_on = e.value
        sw.text = "AUTO ON" if is_on else "AUTO OFF"
        if is_on:
            sw.classes("text-green-400", remove="text-[#9CA3AF]")
        else:
            sw.classes("text-[#9CA3AF]", remove="text-green-400")

    sw.on("update:model-value", _update)
    return sw


def build_commands_panel() -> Any:
    cmd_card = ui.card().classes(
        "cmds w-full h-[240px] min-w-0 overflow-hidden bg-[#0F172A] rounded-xl shadow-lg border border-[#1F2937]"
    )
    with cmd_card:
        ui.label("Commands").classes("text-sm text-[#E5E7EB] font-bold")
        ui.separator().classes("mb-1")

        def clamp(v: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, float(v)))

        GRID = "grid grid-cols-[8rem_5.5rem_3.5rem_1.5rem_1.5rem_auto] items-center gap-2 w-full"

        # 🎯 0) DO Target (새로 추가됨! 소수점 1자리 제어)
        with ui.element("div").classes(GRID + " py-[2px]"):
            ui.label("DO Target").classes("text-xs text-[#9CA3AF] font-semibold")
            # step_val=0.1과 fmt="%.1f"를 넣어서 소수점 1자리 전용으로 만듦
            do_num = _number_box(2.0, 0.0, 10.0, step_val=0.1, fmt="%.1f")
            ui.label("mg/L").classes("text-xs text-[#9CA3AF] text-right")
            _plus_minus(
                lambda: do_num.set_value(round(clamp((do_num.value or 0) - 0.1, 0.0, 10.0), 1)),
                lambda: do_num.set_value(round(clamp((do_num.value or 0) + 0.1, 0.0, 10.0), 1)),
            )
            _apply_btn("Set", "set_do", lambda: float(do_num.value or 0))

        # 1) Air Valve (Valve) - 얘는 정수 제어
        with ui.element("div").classes(GRID + " py-[2px] mt-1"):
            ui.label("Valve Position").classes("text-xs text-[#9CA3AF]")
            air_num = _number_box(100, 0, 100)
            ui.label("%").classes("text-xs text-[#9CA3AF] text-right")
            _plus_minus(
                lambda: air_num.set_value(clamp((air_num.value or 0) - 5, 0, 100)),
                lambda: air_num.set_value(clamp((air_num.value or 0) + 5, 0, 100)),
            )
            _apply_btn("Set", "set_air", lambda: float(air_num.value or 0))

        # 2) Pump Hz - 얘도 정수 제어
        with ui.element("div").classes(GRID + " py-[2px]"):
            ui.label("Pump Speed").classes("text-xs text-[#9CA3AF]")
            hz_num = _number_box(40, 0, 60)
            ui.label("Hz").classes("text-xs text-[#9CA3AF] text-right")
            _plus_minus(
                lambda: hz_num.set_value(clamp((hz_num.value or 0) - 1, 0, 60)),
                lambda: hz_num.set_value(clamp((hz_num.value or 0) + 1, 0, 60)),
            )
            _apply_btn("Set", "set_hz", lambda: float(hz_num.value or 0))

        # 3) Auto Mode (Dummy)
        with ui.row().classes("w-full justify-end mt-2"):
            _auto_switch()

    return cmd_card
