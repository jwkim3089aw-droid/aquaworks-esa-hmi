# app/ui/components/chart.py
from typing import List, Dict, Any, Set, Tuple, Callable, Sequence, MutableMapping, cast, Optional
from nicegui import ui
from nicegui.elements.echart import EChart
import math
from app.stream.state import get_last
from app.ui.common import log, title_of, metric_name_and_unit, axis_label_of


def create_chart_section(
    metrics: List[Dict[str, Any]],
    active_keys: Set[str],
    series_colors_by_key: Dict[str, str],
    on_chart_click: Callable[[Any, List[str], int], None],  # (event, xs_eff, m_eff)
    current_rtu: Optional[Dict[str, int]] = None,  # 🚀 [패치] 다중 장비 파라미터 추가
) -> Tuple[EChart, Any]:

    # 방어 코드: current_rtu가 넘어오지 않았을 경우 기본값 1번 할당
    if current_rtu is None:
        current_rtu = {"id": 1}

    # --- Chart Options Setup ---
    chart_opts: Dict[str, Any] = {
        "backgroundColor": "transparent",
        "animation": False,
        "grid": {"left": 40, "right": 28, "bottom": 10, "top": 84, "containLabel": False},
        "color": [series_colors_by_key[str(m.get("key", title_of(m)))] for m in metrics],
        "legend": {
            "show": True,
            "type": "scroll",
            "orient": "horizontal",
            "top": 0,
            "left": "center",
            "textStyle": {"color": "#9CA3AF", "fontSize": 11},
            "itemWidth": 6,
            "itemHeight": 6,
            "data": [],
        },
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": "rgba(17, 24, 39, 0.9)",
            "borderColor": "#374151",
            "textStyle": {"color": "#F3F4F6", "fontSize": 12},
            "formatter": """
            function (params) {
                if (!params || !params.length) return '';
                var lines = [];
                var first = params[0];
                if (first.axisValue) lines.push(first.axisValue);
                for (var i = 0; i < params.length; i++) {
                    var p = params[i];
                    if (!p || p.value == null || isNaN(p.value)) continue;
                    var v = p.value;
                    if (typeof v === 'string' && (v === '-' || v === '--')) continue;
                    if (typeof v === 'number') {
                        if (p.seriesName.indexOf('MLSS') === 0 || p.seriesName.indexOf('Air Flow') === 0) v = v.toFixed(1);
                        else v = v.toFixed(2);
                    }
                    lines.push(p.marker + ' ' + p.seriesName + ': ' + v);
                }
                return lines.join('<br/>');
            }
            """,
        },
        "xAxis": {
            "type": "category",
            "data": [],
            "boundaryGap": False,
            "axisLine": {"show": True, "lineStyle": {"color": "#4B5563"}},
            "axisTick": {"show": False},
            "splitLine": {"show": False},
            "axisLabel": {"show": True, "color": "#6B7280", "fontSize": 10, "hideOverlap": True},
        },
        "yAxis": [{"type": "value", "show": False}],
        "series": [],
    }

    # Initialize Series
    for m_cfg in metrics:
        base, unit = metric_name_and_unit(m_cfg)
        label = f"{base} ({unit})" if unit else base
        k = str(m_cfg.get("key", title_of(m_cfg)))
        color = series_colors_by_key.get(k)
        s: Dict[str, Any] = {
            "name": label,
            "type": "line",
            "smooth": True,
            "showSymbol": True,
            "symbol": "circle",
            "symbolSize": 8,
            "itemStyle": {"opacity": 0},
            "emphasis": {"itemStyle": {"opacity": 1}},
            "data": [],
            "_key": k,
            "yAxisIndex": 0,
        }
        if color:
            s["linestyle"] = {"width": 1.6, "color": color}
            s["itemStyle"] = {"color": color, "opacity": 0}
        chart_opts["series"].append(s)

    # --- UI Layout ---
    trend_card = ui.card().classes(
        "w-full min-w-0 overflow-hidden bg-[#0F172A] rounded-xl shadow-lg border border-[#1F2937] p-0"
    )

    with trend_card:
        with ui.element("div").classes("relative w-full h-[580px] p-3") as trend_container:
            # Duration Select
            with ui.element("div").classes("absolute top-0 right-3 z-20 flex items-center gap-1"):
                ui.label("Duration:").classes("text-[11px] text-[#9CA3AF]")
                duration_options = [("1분", 60), ("10분", 600), ("30분", 1800), ("1시간", 3600)]
                duration_map = {label: n for label, n in duration_options}
                default_duration_label = "10분"
                duration_select = (
                    ui.select(
                        options=[label for label, _ in duration_options],
                        value=default_duration_label,
                    )
                    .props("dense outlined")
                    .classes("duration-select w-[90px] text-xs text-[#E5E7EB]")
                )

            # The Chart
            _trend_chart = ui.echart(chart_opts).classes("w-full h-full")

            # Click Logic
            def _handle_chart_click(e: Any):
                label = str(duration_select.value or default_duration_label)
                window_n = duration_map.get(label, duration_map[default_duration_label])
                # 🚀 [패치] 클릭 시 현재 선택된 장비(current_rtu["id"])의 데이터만 가져옵니다!
                xs, _ = get_last(current_rtu["id"], window_n)
                xs_list = list(xs)
                total_samples = len(xs_list)
                m_eff = min(total_samples, max(0, window_n))
                if m_eff <= 0:
                    return
                xs_eff = xs_list[-m_eff:]

                # Callback to main to handle data processing and marking
                on_chart_click(e, xs_eff, m_eff)

            _trend_chart.on("chart_bg_click", _handle_chart_click)

            # JS Bridge for click
            ui.timer(
                0.5,
                lambda: ui.run_javascript(
                    f"""
                var chartComp = getElement({_trend_chart.id});
                if (chartComp && chartComp.chart) {{
                    chartComp.chart.getZr().on('click', function(params) {{
                        var pixel = [params.offsetX, params.offsetY];
                        if (chartComp.chart.containPixel('grid', pixel)) {{
                            var idx = chartComp.chart.convertFromPixel({{seriesIndex: 0}}, pixel)[0];
                            if (idx != null) chartComp.$emit('chart_bg_click', {{dataIndex: idx}});
                        }}
                    }});
                }}
            """
                ),
            )

    # --- Update Logic (Tick) ---
    async def _tick_trend() -> None:
        try:
            label = str(duration_select.value or default_duration_label)
            window_n = duration_map.get(label, duration_map[default_duration_label])
            # 🚀 [패치] 차트 갱신 시 현재 선택된 장비(current_rtu["id"])의 데이터만 가져옵니다!
            xs, data = get_last(current_rtu["id"], window_n)
            if not xs:
                return

            xs_list = list(xs)
            total_samples = len(xs_list)
            usable_slots = max(0, window_n)
            m_eff = min(total_samples, usable_slots)
            xs_eff = xs_list[-m_eff:] if m_eff > 0 else []
            x_labels = xs_eff + [""] * (usable_slots - m_eff)

            # Update X-Axis
            trend_opts = cast(MutableMapping[str, Any], _trend_chart.options)
            trend_opts["xAxis"]["data"] = x_labels
            x_len = len(x_labels)

            # Axis & Legend Logic
            key_order = []
            axis_labels_by_key = {}
            legend_labels_by_key = {}
            for m_cfg in metrics:
                k = str(m_cfg.get("key", title_of(m_cfg)))
                key_order.append(k)
                axis_labels_by_key[k] = axis_label_of(m_cfg)
                base, unit = metric_name_and_unit(m_cfg)
                legend_labels_by_key[k] = f"{base} ({unit})" if unit else base

            active_list = [k for k in key_order if k in active_keys] if active_keys else []
            n_axes = len(active_list)
            DEFAULT_STEP = 56
            MAX_SPAN = int(1.7 * DEFAULT_STEP)
            MIN_STEP = 20
            STEP_FOR_3 = max(MIN_STEP, int(MAX_SPAN / 2))
            step = 0 if n_axes <= 1 else (DEFAULT_STEP if n_axes == 2 else STEP_FOR_3)

            axis_index_by_key = {k: idx for idx, k in enumerate(active_list)}
            y_axes = []

            for idx_axis, k_axis in enumerate(active_list):
                y_axes.append(
                    {
                        "type": "value",
                        "position": "left",
                        "offset": idx_axis * step,
                        "name": axis_labels_by_key.get(k_axis, k_axis),
                        "nameLocation": "end",
                        "nameGap": 32,
                        "nameTextStyle": {
                            "align": "center",
                            "verticalAlign": "middle",
                            "fontSize": 11,
                            "lineHeight": 12,
                        },
                        "axisLine": {
                            "show": True,
                            "lineStyle": {"type": "dashed", "color": "#374151"},
                        },
                        "axisTick": {"show": False},
                        "splitLine": {"show": False},
                        "axisLabel": {"color": "#6B7280", "fontSize": 10},
                    }
                )

            if not y_axes:
                y_axes = [
                    {
                        "type": "value",
                        "show": False,
                        "axisLine": {"show": False},
                        "axisTick": {"show": False},
                        "splitLine": {"show": False},
                        "axisLabel": {"show": False},
                    }
                ]
            trend_opts["yAxis"] = y_axes

            legend_data = []
            if active_keys:
                for k in key_order:
                    if k in active_keys:
                        c = series_colors_by_key.get(k, "#9CA3AF")
                        legend_data.append(
                            {
                                "name": legend_labels_by_key[k],
                                "textStyle": {"color": c, "fontWeight": "bold"},
                            }
                        )

            legend_cfg = cast(Dict[str, Any], trend_opts.get("legend") or {})
            legend_cfg["show"] = bool(legend_data)
            legend_cfg["data"] = legend_data
            trend_opts["legend"] = legend_cfg

            # Update Series Data
            series_list = cast(List[Dict[str, Any]], trend_opts.get("series") or [])
            for idx, m_cfg in enumerate(metrics):
                k = str(m_cfg.get("key", title_of(m_cfg)))
                vals_raw = list(data.get(k, []))
                n_vals = len(vals_raw)

                if n_vals > total_samples:
                    vals_raw = vals_raw[-total_samples:]
                elif n_vals < total_samples:
                    vals_raw = [None] * (total_samples - n_vals) + vals_raw

                vals_eff = vals_raw[-m_eff:] if m_eff > 0 else []
                if len(vals_eff) < m_eff:
                    vals_eff = [None] * (m_eff - len(vals_eff)) + vals_eff

                is_active = bool(active_keys) and (k in active_keys)
                vals_display = (
                    ([None] * 0 + vals_eff + [None] * (usable_slots - m_eff))
                    if is_active
                    else [None] * x_len
                )

                if idx >= len(series_list):
                    series_list.append({})
                s = series_list[idx]
                s["data"] = vals_display
                s["showSymbol"] = True
                s["symbol"] = "circle"
                s["symbolSize"] = 8
                s.setdefault("itemStyle", {})
                s["itemStyle"]["opacity"] = 0
                s["yAxisIndex"] = axis_index_by_key.get(k, 0)
                s.setdefault("tooltip", {})
                s["tooltip"]["show"] = bool(is_active)
                if "markLine" in s:
                    s.pop("markLine", None)

            trend_opts["series"] = series_list
            _trend_chart.update()
        except Exception as e:
            log.error(f"Chart Update Error: {e}")

    return _trend_chart, _tick_trend
