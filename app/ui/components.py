# app/ui/components.py
from __future__ import annotations

from typing import Any

from nicegui import ui


def metric_card(title: str) -> tuple[Any, Any, Any]:
    """클릭 가능한 KPI 카드: (card_element, value_label, sparkline_echart) 반환"""
    card = ui.card().classes(
        "bg-black/30 text-white min-w-[200px] w-full cursor-pointer " "hover:bg-black/40 transition"
    )
    with card:
        ui.label(title).classes("text-xs opacity-70")
        val = ui.label("--").classes("text-2xl font-semibold")
        spark = ui.echart(
            {
                "backgroundColor": "transparent",
                "grid": {"left": 0, "right": 0, "top": 4, "bottom": 0},
                "xAxis": {
                    "type": "category",
                    "data": [],
                    "axisLabel": {"show": False},
                    "axisLine": {"show": False},
                },
                "yAxis": {
                    "type": "value",
                    "axisLabel": {"show": False},
                    "axisLine": {"show": False},
                    "splitLine": {"show": False},
                },
                "series": [
                    {"type": "line", "data": [], "showSymbol": False, "lineStyle": {"width": 1}}
                ],
                "tooltip": {"show": False},
            }
        ).classes("w-full h-[44px] mt-1")
    return card, val, spark
