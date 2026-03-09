# app/ui/controls.py
from __future__ import annotations
from typing import Dict, Any, Tuple
from nicegui import ui
from .config import BUCKETS, FONT_SCALES


def build_top_controls(
    root: Any, font_scales: Dict[str, int] = FONT_SCALES
) -> Tuple[Any, Any, Any, Any]:
    """상단 컨트롤바: Hours / Bucket / Scale / Dark"""
    with ui.row().classes("items-center gap-8 w-full justify-end"):
        ui.label("Hours").classes("text-[#9CA3AF]")
        inp_hours = ui.input(value="0.5").props("type=number dense outlined").classes("w-20")

        ui.label("Bucket").classes("ml-6 text-[#9CA3AF]")
        sel_bucket = ui.select(BUCKETS, value="5 s").props("dense outlined").classes("w-28")

        ui.label("M").classes("ml-6 text-[#9CA3AF]")
        sel_scale = ui.select(["M"], value="M").props("dense outlined").classes("w-14")

        ui.label("Dark").classes("ml-6 text-[#9CA3AF]")
        sw_dark = ui.switch(value=True)
    return inp_hours, sel_bucket, sel_scale, sw_dark
