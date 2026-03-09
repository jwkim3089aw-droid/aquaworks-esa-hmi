# app/ui/commands.py
# UI 공용 "Commands" 패널 컴포넌트 빌더
from __future__ import annotations

from typing import Callable, Any, Tuple
from nicegui import ui

NumberGetter = Callable[[], float]
OnApply = Callable[[str, float], None]  # (label, value) -> None


def _number_box(value: float, lo: float, hi: float) -> Any:
    """숫자 박스 UI (중앙정렬, dense)."""
    return (
        ui.number(value=value, min=lo, max=hi, step=1, format='%.0f')
        .props('outlined dense input-class=text-center')
        .classes('w-[88px]')
    )


def _pm_text(char: str, on_click: Callable[[], None]) -> Any:
    """+/- 라벨 버튼 (main.py의 전역 CSS .pm-txt와 호환)."""
    el = ui.label(char).classes('pm-txt')
    el.on('click', lambda _e: on_click())
    return el


def _plus_minus(on_minus: Callable[[], None], on_plus: Callable[[], None]) -> Tuple[Any, Any]:
    return _pm_text('−', on_minus), _pm_text('+', on_plus)


def _apply_btn(label: str, get_val: NumberGetter, on_apply: OnApply) -> Any:
    return (
        ui.button('적용', icon='check', color='primary')
        .props('unelevated dense')
        .on('click', lambda _e: on_apply(label, float(get_val() or 0)))
    )


def build_commands_panel(on_apply: OnApply) -> Any:
    """
    Commands 카드 빌더.
    on_apply(label, value) 콜백으로 외부(예: history)에 로깅/처리를 위임.
    """
    cmd_card = ui.card().classes(
        'cmds w-full h-[240px] min-w-0 overflow-hidden bg-[#0F172A] rounded-xl shadow-lg border border-[#1F2937]'
    )
    with cmd_card:
        ui.label('Commands').classes('text-sm text-[#E5E7EB]')
        ui.separator().classes('mb-1')

        def clamp(v: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, float(v)))

        GRID = 'grid grid-cols-[8rem_5.5rem_3.5rem_1.5rem_1.5rem_auto] items-center gap-2 w-full'

        # Air
        with ui.element('div').classes(GRID + ' py-[2px]'):
            ui.label('Air Setpoint').classes('text-xs text-[#9CA3AF]')
            air_num = _number_box(180, 0, 300)
            ui.label('L/min').classes('text-xs text-[#9CA3AF] text-right')
            _plus_minus(
                lambda: air_num.set_value(clamp((air_num.value or 0) - 1, 0, 300)),
                lambda: air_num.set_value(clamp((air_num.value or 0) + 1, 0, 300)),
            )
            _apply_btn('Air Set', lambda: float(air_num.value or 0), on_apply)

        # Pump Hz
        with ui.element('div').classes(GRID + ' py-[2px]'):
            ui.label('Pump Hz Setpoint').classes('text-xs text-[#9CA3AF]')
            hz_num = _number_box(40, 20, 60)
            ui.label('Hz').classes('text-xs text-[#9CA3AF] text-right')
            _plus_minus(
                lambda: hz_num.set_value(clamp((hz_num.value or 0) - 1, 20, 60)),
                lambda: hz_num.set_value(clamp((hz_num.value or 0) + 1, 20, 60)),
            )
            _apply_btn('Pump Hz', lambda: float(hz_num.value or 0), on_apply)

    return cmd_card
