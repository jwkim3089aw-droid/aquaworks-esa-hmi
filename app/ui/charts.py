# app/ui/charts.py
# [CHANGED] 불필요한 ui import 제거, 타입 주석 정리
from __future__ import annotations

from collections.abc import Sequence  # [ADDED]
from typing import Any


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
            "axisLine": {"lineStyle": {"color": "#888"}},
            "axisLabel": {"color": "#bbb"},
            "splitLine": {"lineStyle": {"color": "#333"}},
            "scale": True,
        }
        if meta["key"] == "pH":
            axis_conf["min"] = 6.5
            axis_conf["max"] = 7.5
            axis_conf["scale"] = False
        y_axes.append(axis_conf)

    series: list[dict[str, Any]] = [
        {
            "name": meta["label"],
            "type": "line",
            "yAxisIndex": meta["axis"],
            "showSymbol": False,
            "data": [],
        }
        for meta in metrics
    ]

    return {
        "backgroundColor": "transparent",
        "tooltip": {"trigger": "axis"},
        "legend": {
            "type": "scroll",
            "orient": "horizontal",
            "top": 0,
            "data": [m["label"] for m in metrics],
            "textStyle": {"color": "#ddd"},
        },
        "grid": {"left": 50, "right": 50, "bottom": 40, "top": 30},
        "xAxis": {
            "type": "category",
            "data": [],
            "axisLine": {"lineStyle": {"color": "#888"}},
            "axisLabel": {"color": "#bbb"},
        },
        "yAxis": y_axes,
        "series": series,
        "title": {
            "show": False,
            "text": "데이터 없음",
            "left": "center",
            "top": "center",
            "textStyle": {"color": "#aaa"},
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
