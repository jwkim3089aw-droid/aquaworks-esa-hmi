# app/ui/history_dialog.py
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Set

from nicegui import ui
from app.services.history import fetch_history_data
from app.ui.config import METRICS

log = logging.getLogger("esa_hmi.history")

# 차트 색상 팔레트
COLORS = [
    "#3399FF",
    "#66FF99",
    "#FF6666",
    "#FFCC33",
    "#00FFFF",
    "#CC99FF",
    "#FF9966",
    "#FF66CC",
    "#99CC00",
]


def create_history_dialog() -> ui.dialog:

    # -----------------------------------------------------------
    # [CSS] 달력 아이콘 반전 (다크모드 대응)
    # -----------------------------------------------------------
    ui.add_head_html(
        """
        <style>
            input[type="datetime-local"]::-webkit-calendar-picker-indicator {
                filter: invert(1);
                opacity: 0.6;
                cursor: pointer;
            }
            input[type="datetime-local"]::-webkit-calendar-picker-indicator:hover {
                opacity: 1;
            }
        </style>
    """
    )

    # --- State ---
    cached_data: Dict[str, Any] | None = None
    selected_keys: Set[str] = set()

    # Metric Meta Setup
    metric_info = {}
    metric_order = []

    for idx, m in enumerate(METRICS):
        key = str(m["key"])
        metric_order.append(key)
        full_label = str(m.get("label") or key.upper())
        unit = str(m.get("unit", ""))
        name_only = full_label.split("(")[0].strip() if "(" in full_label else full_label

        metric_info[key] = {
            "label_full": full_label,
            "name": name_only,
            "unit_display": f"({unit})" if unit else "",
            "color": COLORS[idx % len(COLORS)],
        }

    chart_ref: Any = None
    toggles_container: Any = None

    # --- Data Matcher ---
    def get_series_data_safe(target_key: str) -> list:
        if not cached_data or "series" not in cached_data:
            return []
        series_map = cached_data["series"]

        # 정확히 일치하는 키가 있으면 반환
        if target_key in series_map:
            return series_map[target_key]

        # 대소문자나 공백이 달라도 최대한 찾아봄 (Fallback)
        def normalize(s: str):
            return str(s).lower().replace("_", "").replace(" ", "")

        target_norm = normalize(target_key)
        for db_key, vals in series_map.items():
            if normalize(db_key) == target_norm:
                return vals
        return []

    # --- Chart Renderer ---
    def update_chart():
        if not cached_data or not chart_ref:
            return

        if not selected_keys:
            chart_ref.options["series"] = []
            chart_ref.options["yAxis"] = [{"type": "value", "show": False}]
            chart_ref.update()
            return

        active_keys = [k for k in metric_order if k in selected_keys]
        y_axes = []
        series_list = []
        AXIS_WIDTH = 50

        for idx, key in enumerate(active_keys):
            info = metric_info[key]
            vals = get_series_data_safe(key)
            offset = idx * AXIS_WIDTH
            axis_name = (
                f"{info['name']}\n{info['unit_display']}" if info["unit_display"] else info["name"]
            )

            y_axes.append(
                {
                    "type": "value",
                    "name": axis_name,
                    "nameLocation": "end",
                    "nameGap": 12,
                    "position": "left",
                    "offset": offset,
                    "axisLine": {"show": True, "lineStyle": {"color": info["color"]}},
                    "axisLabel": {
                        "color": info["color"],
                        "fontSize": 11,
                        "fontWeight": "bold",
                        "formatter": "{value}",
                        "hideOverlap": True,
                    },
                    "splitLine": {"show": idx == 0, "lineStyle": {"color": "#333", "opacity": 0.2}},
                    "nameTextStyle": {
                        "color": info["color"],
                        "align": "center",
                        "verticalAlign": "bottom",
                        "padding": [0, 0, 5, 0],
                        "fontWeight": "bold",
                        "fontSize": 11,
                    },
                    "scale": True,
                }
            )

            series_list.append(
                {
                    "name": info["label_full"],
                    "type": "line",
                    "data": vals,
                    "yAxisIndex": idx,
                    "showSymbol": False,
                    "connectNulls": True,  # None 값이어도 선 연결 (원하면 False로 변경)
                    "smooth": True,
                    "itemStyle": {"color": info["color"]},
                    "lineStyle": {"width": 1.5},
                }
            )

        grid_left = (len(active_keys) * AXIS_WIDTH) + 20
        chart_ref.options["xAxis"]["data"] = cached_data.get("times", [])
        chart_ref.options["yAxis"] = y_axes
        chart_ref.options["series"] = series_list
        chart_ref.options["grid"]["left"] = grid_left
        chart_ref.update()

    # --- Sidebar Controls ---
    def render_toggles():
        if not toggles_container:
            return
        toggles_container.clear()
        with toggles_container:
            ui.label("TAGS").classes(
                "text-[12px] text-gray-500 font-bold mb-3 tracking-widest text-center w-full"
            )
            for key in metric_order:
                info = metric_info[key]
                is_active = key in selected_keys

                def _on_toggle(k=key):
                    if k in selected_keys:
                        selected_keys.remove(k)
                    else:
                        selected_keys.add(k)
                    render_toggles()
                    update_chart()

                bg_class = "bg-white/10" if is_active else "bg-transparent hover:bg-white/5"
                text_color = info["color"] if is_active else "#64748B"
                bar_color = info["color"] if is_active else "transparent"

                with (
                    ui.element("div")
                    .classes(
                        f"w-full mb-1 cursor-pointer rounded flex items-center h-8 transition-all duration-200 {bg_class}"
                    )
                    .on("click", _on_toggle)
                ):
                    ui.element("div").style(
                        f"width: 3px; height: 100%; background-color: {bar_color}; border-radius: 3px 0 0 3px;"
                    )
                    with ui.row().classes(
                        "flex-1 items-center justify-between px-2 overflow-hidden"
                    ):
                        ui.label(info["name"]).style(f"color: {text_color}").classes(
                            f"text-xs {'font-bold' if is_active else 'font-normal'} tracking-wide truncate"
                        )
                    if is_active:
                        ui.icon("check", size="xs").style(
                            f"color: {info['color']}; font-size: 14px;"
                        ).classes("mr-2")

    # =========================================================================
    # DIALOG LAYOUT
    # =========================================================================
    with (
        ui.dialog() as dialog,
        ui.card().classes(
            "w-[95vw] h-[90vh] max-w-[1600px] bg-[#0B1121] border border-[#1F2937] p-0 flex flex-col shadow-2xl rounded-lg"
        ),
    ):

        # 1. HEADER
        with ui.element("div").classes(
            "w-full h-[50px] flex items-center relative px-4 bg-[#161F32] border-b border-[#1F2937]"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("ssid_chart", size="xs", color="blue-400")
                ui.label("HISTORY").classes("text-md font-bold text-gray-100 tracking-wide")

            with ui.row().classes("absolute left-1/2 -translate-x-1/2 items-center gap-2"):
                input_props = 'type=datetime-local dense outlined input-style="color:white; font-size:13px; text-align:center;"'
                input_class = "w-48 bg-[#0F172A] rounded"
                now = datetime.now()
                d_start = (
                    ui.input(value=(now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"))
                    .props(input_props)
                    .classes(input_class)
                )
                ui.label("~").classes("text-gray-500 font-bold")
                d_end = (
                    ui.input(value=now.strftime("%Y-%m-%d %H:%M"))
                    .props(input_props)
                    .classes(input_class)
                )

                async def _search():
                    if not d_start.value or not d_end.value:
                        return
                    try:
                        dt_s = datetime.fromisoformat(d_start.value.replace("T", " "))
                        dt_e = datetime.fromisoformat(d_end.value.replace("T", " "))
                    except:
                        ui.notify("Invalid date", type="negative")
                        return

                    if (dt_e - dt_s).total_seconds() > 30 * 24 * 3600:
                        ui.notify("기간이 너무 깁니다 (최대 30일)", type="warning")
                        return

                    ui.notify("Loading InfluxDB Data...", type="info", spinner=True)
                    nonlocal cached_data
                    cached_data = await asyncio.to_thread(fetch_history_data, dt_s, dt_e)

                    if not cached_data or not cached_data["times"]:
                        ui.notify("No Data Found.", type="warning")
                        return

                    if not selected_keys:
                        selected_keys.add(metric_order[0])
                    render_toggles()
                    update_chart()
                    ui.notify(f"Loaded {len(cached_data['times'])} pts.", type="positive")

                ui.button("SEARCH", on_click=_search, icon="search").props(
                    "unelevated dense color=blue-600"
                ).classes("px-4 ml-1 h-[32px]")

            with ui.row().classes("ml-auto"):
                ui.button(icon="close", on_click=dialog.close).props(
                    "flat round dense color=gray-400 hover-color=white"
                )

        # 2. BODY
        with ui.row().classes("w-full flex-1 min-h-0 gap-0"):
            with ui.column().classes(
                "w-[160px] h-full p-3 bg-[#0F1522] border-r border-[#1F2937] overflow-y-auto"
            ) as toggles_container:
                pass
            with ui.column().classes("flex-1 h-full p-0 relative bg-[#0B1121]"):
                chart_ref = ui.echart(
                    {
                        "backgroundColor": "transparent",
                        "animation": False,
                        "tooltip": {
                            "trigger": "axis",  # [중요] 아이템이 아닌 축 기준 트리거
                            "axisPointer": {
                                "type": "cross",  # 가이드라인 표시
                                "label": {"backgroundColor": "#334155"},
                            },
                            "backgroundColor": "rgba(15, 23, 42, 0.95)",
                            "borderColor": "#334155",
                            "textStyle": {"color": "#F8FAFC", "fontSize": 12},
                            "confine": True,  # 툴팁이 차트 밖으로 나가지 않게 제한
                            "order": "seriesAsc",  # 툴팁 내 데이터 표시 순서
                            ":formatter": """
                                function (params) {
                                    if (!params.length) return '';
                                    var s = params[0].axisValue + '<br/>';
                                    for (var i = 0; i < params.length; i++) {
                                        var p = params[i];
                                        var val = p.value;
                                        if (typeof val === 'number') {
                                            // MLSS, Air Flow, Pump Hz 등은 소수점 1자리
                                            if (p.seriesName.indexOf('MLSS') > -1 ||
                                                p.seriesName.indexOf('Air') > -1 ||
                                                p.seriesName.indexOf('Hz') > -1) {
                                                val = val.toFixed(1);
                                            } else {
                                                // 나머지는 소수점 2자리 (DO, pH, Temp, Power 등)
                                                val = val.toFixed(2);
                                            }
                                        }
                                        s += p.marker + ' ' + p.seriesName + ': <b>' + val + '</b><br/>';
                                    }
                                    return s;
                                }
                            """,
                        },
                        "grid": {
                            "left": 60,
                            "right": 30,
                            "top": 70,
                            "bottom": 40,
                            "containLabel": False,
                        },
                        "dataZoom": [
                            {"type": "inside", "xAxisIndex": 0},
                            {"type": "inside", "yAxisIndex": "all"},
                        ],
                        "xAxis": {
                            "type": "category",
                            "data": [],
                            "boundaryGap": False,
                            "axisLine": {"lineStyle": {"color": "#334155"}},
                            "axisLabel": {"color": "#94A3B8", "margin": 14},
                        },
                        "yAxis": [{"type": "value", "show": False}],
                        "series": [],
                    }
                ).classes("w-full h-full")

    render_toggles()
    return dialog
