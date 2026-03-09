# app/ui/dialogs.py
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from app.ui.charts import build_trend_options


def create_single_dialog(
    metrics: list[dict[str, Any]],
) -> tuple[Any, Any, Callable[[str], None], Callable[[], str | None]]:
    single_state: dict[str, str | None] = {"key": None}
    with ui.dialog() as single_dialog, ui.card().classes("aw-panel p-4 w-[1200px] max-w-[98vw]"):
        single_title = ui.label("Metric").classes("aw-title text-lg mb-2")
        trend_single: Any = ui.echart(
            {
                "backgroundColor": "transparent",
                "tooltip": {"trigger": "axis"},
                "grid": {"left": 56, "right": 40, "bottom": 48, "top": 36},
                "xAxis": {
                    "type": "category",
                    "data": [],
                    "axisLine": {"lineStyle": {"color": "#334155"}},
                    "axisLabel": {"color": "#94a3b8"},
                },
                "yAxis": {
                    "type": "value",
                    "name": "",
                    "axisLine": {"lineStyle": {"color": "#334155"}},
                    "axisLabel": {"color": "#94a3b8"},
                },
                "series": [
                    {"name": "", "type": "line", "showSymbol": False, "data": [], "smooth": True}
                ],
            }
        ).classes("w-[1140px] h-[520px]")
        ui.button("닫기", on_click=single_dialog.close).classes("aw-btn mt-3")

    def open_single_dialog(key: str) -> None:
        single_state["key"] = key
        meta = next((m for m in metrics if m["key"] == key), None)
        if meta:
            single_title.text = f'Realtime Trend · {meta["label"]}'
            trend_single.options["yAxis"]["name"] = meta["label"]
            trend_single.options["series"][0]["name"] = meta["label"]
        single_dialog.open()

    def current_key() -> str | None:
        return single_state["key"]

    return single_dialog, trend_single, open_single_dialog, current_key


def create_full_trend_dialog(
    metrics: list[dict[str, Any]], axis_positions: list[tuple[str, int]]
) -> tuple[Any, Any]:
    with ui.dialog() as trend_dialog, ui.card().classes("aw-panel p-4 w-[1280px] max-w-[98vw]"):
        ui.label("Realtime Trend (DO, Air (L/min), MLSS, Temp, pH, Power)").classes(
            "aw-title text-lg mb-2"
        )
        trend_full: Any = ui.echart(build_trend_options(metrics, axis_positions)).classes(
            "w-[1220px] h-[560px]"
        )
        ui.button("닫기", on_click=trend_dialog.close).classes("aw-btn mt-3")
    return trend_dialog, trend_full
