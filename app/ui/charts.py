# app/ui/charts.py
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

# [CHANGED] 다크에서 잘 보이는 팔레트
_PALETTE = ["#14b8a6", "#60a5fa", "#22d3ee", "#34d399", "#fbbf24", "#a78bfa"]


def build_trend_options(
    metrics: Sequence[dict[str, Any]],
    axis_positions: Sequence[tuple[str, int]],
) -> dict[str, Any]:
    y_axes: list[dict[str, Any]] = []
    for i, meta in enumerate(metrics):
        pos, offset = axis_positions[i]
        axis_conf: dict[str, Any] = {
            "type": "value",
            "name": meta["label"],
            "position": pos,
            "offset": offset,
            "axisLine": {"lineStyle": {"color": "#334155"}},  # [CHANGED]
            "axisLabel": {"color": "#94a3b8"},  # [CHANGED]
            "splitLine": {"lineStyle": {"color": "#1f2937"}},  # [CHANGED]
            "scale": True,
        }
        if meta["key"] == "pH":
            axis_conf["min"] = 6.5
            axis_conf["max"] = 7.5
            axis_conf["scale"] = False
        y_axes.append(axis_conf)

    series: list[dict[str, Any]] = []
    for meta in metrics:  # [CHANGED] idx 제거
        series.append(
            {
                "name": meta["label"],
                "type": "line",
                "smooth": True,
                "yAxisIndex": meta["axis"],
                "showSymbol": False,
                "data": [],
                "lineStyle": {"width": 2},
            }
        )

    return {
        "color": _PALETTE,
        "backgroundColor": "transparent",
        "tooltip": {"trigger": "axis"},
        "legend": {
            "type": "plain",
            "top": 0,
            "data": [m["label"] for m in metrics],
            "textStyle": {"color": "#cbd5e1"},  # [CHANGED]
        },
        # [CHANGED] 여백 튜닝 (라벨 겹침 방지)
        "grid": {"left": 56, "right": 56, "bottom": 40, "top": 30},
        "xAxis": {
            "type": "category",
            "data": [],
            "axisLine": {"lineStyle": {"color": "#334155"}},  # [CHANGED]
            "axisLabel": {"color": "#94a3b8"},  # [CHANGED]
        },
        "yAxis": y_axes,
        "series": series,
        "title": {
            "show": False,
            "text": "No data",
            "left": "center",
            "top": "center",
            "textStyle": {"color": "#64748b"},
        },
    }


def short_ts(s: Any) -> str:
    s = str(s or "")
    return s[-8:] if len(s) >= 8 else s


async def update_multi_metric_chart(
    chart: Any,
    metrics: Sequence[dict[str, Any]],
    xs: list[str],
    rows: list[dict[str, Any]],
) -> None:
    chart.options["xAxis"]["data"] = xs
    for i, meta in enumerate(metrics):
        chart.options["series"][i]["data"] = [row.get(meta["key"]) for row in rows]
    await chart.update()
