# app/ui/metrics.py
from __future__ import annotations
from typing import Tuple, Any, Dict, Optional
from nicegui import ui
import re


def _spark_options() -> Dict[str, Any]:
    """ECharts 스파크라인 옵션"""
    opts: Dict[str, Any] = {
        "grid": {"left": 0, "right": 0, "top": 0, "bottom": 0},
        "xAxis": {"type": "category", "show": False, "data": []},
        "yAxis": {"type": "value", "show": False},
        "series": [
            {
                "type": "line",
                "data": [],
                "smooth": True,
                "showSymbol": False,
                "lineStyle": {"width": 1},
            }
        ],
        "animation": False,
    }
    return opts


def create_metric_card(
    title: str,
    unit: str,
    *,
    compact: bool = True,
    width_px: Optional[int] = None,
) -> Tuple[Any, Any, Any, Any]:
    """KPI 카드: (card, value_label, unit_label, spark_chart) 반환
    - 타이틀의 괄호 단위(예: 'Temp (°C)')는 제거하여 표시
    - 값 우측의 단위 라벨은 그대로 유지
    - width_px로 카드 가로 고정 가능 (예: 240)
    """
    title_clean = re.sub(r"\s*\([^)]*\)", "", title).strip()

    w_class = f"w-[{width_px}px]" if width_px else "w-full"
    card = ui.card().classes(
        f"{w_class} h-[90px] bg-[#0F172A] rounded-xl shadow-lg border border-[#1F2937] px-2 pt-1"
    )
    with card:
        ui.label(title_clean).classes("text-[15px] font-medium text-[#9CA3AF]")
        with ui.row().classes("items-end mt-0"):
            v = ui.label("--").classes(
                "text-3xl md:text-4xl font-semibold text-white/90 leading-none"
            )
            u = ui.label(unit or " ").classes(
                "text-xs md:text-sm text-[#9CA3AF] leading-none translate-y-[-2px]"
            )
            spark = None
    return card, v, u, spark
