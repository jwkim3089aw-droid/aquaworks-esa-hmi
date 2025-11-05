# app/ui/controls.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from nicegui import ui

if TYPE_CHECKING:
    from nicegui.events import ValueChangeEventArguments as VArgs  # type: ignore
else:
    VArgs = Any  # type: ignore


def build_top_controls(root: Any, font_scales: dict[str, int]) -> tuple[Any, Any]:
    header = ui.row().classes("items-center justify-between w-full")
    with header:
        ui.label("ESA HMI").classes("aw-title text-xl")

        with ui.row().classes("items-center gap-4"):
            ui.label("Hours").classes("aw-subtle text-xs")
            inp_hours = ui.number(value=0.5, min=0.05, max=24, step=0.05).classes("w-[120px]")

            ui.label("Bucket").classes("aw-subtle text-xs")
            sel_bucket = ui.select(
                {1: "1 s", 2: "2 s", 5: "5 s", 10: "10 s", 15: "15 s", 30: "30 s", 60: "60 s"},
                value=5,
            ).classes("w-[120px]")

            sel_font = ui.select({"S": "S", "M": "M", "L": "L"}, value="M").classes("w-[88px]")

            def apply_font(v: str) -> None:
                px = font_scales.get(v, font_scales["M"])
                root.style(f"font-size: {px}px")

            sel_font.on_value_change(lambda e: apply_font(cast(str, e.value)))

            # [CHANGED] 다크 기본 ON, 토글 유지
            sw_dark = ui.switch("Dark", value=True)

            def on_dark_change(e: VArgs) -> None:
                if bool(getattr(e, "value", True)):
                    ui.dark_mode().enable()
                else:
                    ui.dark_mode().disable()

            sw_dark.on_value_change(on_dark_change)

    return inp_hours, sel_bucket
