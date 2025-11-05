# app/ui/charts.py
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

_PALETTE = ["#10a5a5", "#2563eb", "#0ea5e9", "#0ea37a", "#f59e0b", "#7c3aed"]


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
            "axisLine": {"lineStyle": {"color": "#c2cfe0"}},
            "axisLabel": {"color": "#64748b"},
            "splitLine": {"lineStyle": {"color": "#eef2f7"}},
            "scale": True,
        }
        if meta["key"] == "pH":
            axis_conf["min"] = 6.5
            axis_conf["max"] = 7.5
            axis_conf["scale"] = False
        y_axes.append(axis_conf)

    series: list[dict[str, Any]] = []
    for meta in metrics:
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
            "textStyle": {"color": "#475569"},
        },
        "grid": {"left": 48, "right": 48, "bottom": 36, "top": 28},
        "xAxis": {
            "type": "category",
            "data": [],
            "axisLine": {"lineStyle": {"color": "#c2cfe0"}},
            "axisLabel": {"color": "#64748b"},
        },
        "yAxis": y_axes,
        "series": series,
        "title": {
            "show": False,
            "text": "No data",
            "left": "center",
            "top": "center",
            "textStyle": {"color": "#94a3b8"},
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
