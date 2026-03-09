# app/ui/components.py
from __future__ import annotations
from typing import Any
from nicegui import ui


def metric_card(title: str) -> tuple[Any, Any, Any]:
    """KPI 카드(스파크 포함)"""
    card = ui.card().classes("aw-card p-4 min-w-[220px] w-full cursor-pointer")
    with card:
        ui.label(title).classes("text-xs aw-subtle")
        val = ui.label("--").classes("text-3xl font-semibold mt-1")
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
                    {
                        "type": "line",
                        "data": [],
                        "showSymbol": False,
                        "smooth": True,
                        "lineStyle": {"width": 2, "color": "#14b8a6"},
                        "areaStyle": {"opacity": 0.12, "color": "#14b8a6"},
                    }
                ],
                "tooltip": {"show": False},
            }
        ).classes("w-full h-[46px] mt-2")
    return card, val, spark
