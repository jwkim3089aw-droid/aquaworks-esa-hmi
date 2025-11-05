# app/ui/controls.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast  # [CHANGED]

from nicegui import ui

# NiceGUI 버전에 따라 이벤트 타입명이 다를 수 있어요.
# 타입체커용으로만 ValueChangeEventArguments를 쓰고, 런타임은 Any로 둡니다.  # [ADDED]
if TYPE_CHECKING:
    from nicegui.events import ValueChangeEventArguments as VArgs  # type: ignore
else:
    VArgs = Any  # type: ignore


def build_top_controls(root: Any, font_scales: dict[str, int]) -> tuple[Any, Any]:
    with ui.row().classes("items-center justify-between w-full"):
        with ui.row().classes("items-center gap-4"):
            ui.icon("schedule").classes("text-white/70")
            inp_hours = ui.number(label="Hours", value=0.5, min=0.05, max=24, step=0.05).classes(
                "w-[140px]"
            )
            sel_bucket = ui.select(
                {1: "1 s", 2: "2 s", 5: "5 s", 10: "10 s", 15: "15 s", 30: "30 s", 60: "60 s"},
                value=5,
                label="Bucket",
            ).classes("w-[140px]")

        with ui.row().classes("items-center gap-4"):
            sw_dark = ui.switch("Dark", value=True).classes("text-white/70")

            def on_dark_change(e: VArgs) -> None:  # [CHANGED] 명시 타입
                # e.value가 bool이라고 가정하지만, 보수적으로 캐스팅  # [ADDED]
                val = cast(bool, getattr(e, "value", True))
                if val:
                    ui.dark_mode().enable()
                else:
                    ui.dark_mode().disable()

            sw_dark.on_value_change(on_dark_change)

            sel_font = ui.select({"S": "S", "M": "M", "L": "L"}, value="M", label="Font").classes(
                "w-[100px]"
            )

            def apply_font(v: str) -> None:
                px = font_scales.get(v, font_scales["M"])
                root.style(f"font-size: {px}px")

            def on_font_change(e: VArgs) -> None:  # [CHANGED]
                apply_font(cast(str, getattr(e, "value", "M")))

            sel_font.on_value_change(on_font_change)

    return inp_hours, sel_bucket
