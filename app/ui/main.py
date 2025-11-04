# app/ui/main.py
from __future__ import annotations

import asyncio
from typing import Any, cast

import httpx
from nicegui import ui

# =========================
# CONFIG
# =========================
API_BASE = "http://127.0.0.1:8003"

# 메트릭 메타데이터 (라벨/단위/축 인덱스)
# axis: 0~5 (다중 y축; 좌/우/오프셋 분리 배치)
METRICS: list[dict[str, Any]] = [
    {"key": "DO", "label": "DO (mg/L)", "axis": 0, "unit": "mg/L"},
    {"key": "air_flow", "label": "Air Flow (L/min)", "axis": 1, "unit": "L/min"},
    {"key": "MLSS", "label": "MLSS (mg/L)", "axis": 2, "unit": "mg/L"},
    {"key": "power", "label": "Power (kW)", "axis": 3, "unit": "kW"},
    {"key": "temp", "label": "Temp (°C)", "axis": 4, "unit": "°C"},
    {"key": "pH", "label": "pH", "axis": 5, "unit": ""},
]

# y축 배치(좌/우/오프셋)
AXIS_POSITIONS = [
    ("left", 0),  # DO
    ("right", 0),  # Air
    ("left", 55),  # MLSS
    ("right", 55),  # Power
    ("left", 110),  # Temp
    ("right", 110),  # pH
]

# =========================
# THEME
# =========================
ui.dark_mode().enable()
ui.colors(primary="teal")


# =========================
# SMALL HELPERS
# =========================
def metric_card(title: str):
    """클릭 가능한 KPI 카드: (card_element, value_label)를 반환"""
    card = ui.card().classes(
        "bg-black/30 text-white min-w-[160px] cursor-pointer " "hover:bg-black/40 transition"
    )
    with card:
        ui.label(title).classes("text-xs opacity-70")
        val = ui.label("--").classes("text-2xl font-semibold")
    return card, val


def build_trend_options() -> dict[str, Any]:
    """메인 트렌드 ECharts 옵션 (6라인 토글)"""
    y_axes: list[dict[str, Any]] = []
    for i, meta in enumerate(METRICS):
        pos, offset = AXIS_POSITIONS[i]
        y_axes.append(
            {
                "type": "value",
                "name": meta["label"],
                "position": pos,
                "offset": offset,
                "axisLine": {"lineStyle": {"color": "#888"}},
                "axisLabel": {"color": "#bbb"},
                "splitLine": {"lineStyle": {"color": "#333"}},
            }
        )

    series: list[dict[str, Any]] = []
    # [CHANGED] B007 해결: i를 쓰지 않으므로 enumerate 제거
    for meta in METRICS:
        series.append(
            {
                "name": meta["label"],
                "type": "line",
                "yAxisIndex": meta["axis"],
                "showSymbol": False,
                "data": [],
            }
        )

    return {
        "backgroundColor": "transparent",
        "tooltip": {"trigger": "axis"},
        "legend": {"data": [m["label"] for m in METRICS], "textStyle": {"color": "#ddd"}},
        "grid": {"left": 50, "right": 50, "bottom": 40, "top": 30},
        "xAxis": {
            "type": "category",
            "data": [],
            "axisLine": {"lineStyle": {"color": "#888"}},
            "axisLabel": {"color": "#bbb"},
        },
        "yAxis": y_axes,
        "series": series,
    }


# =========================
# TOP CONTROLS
# =========================
with ui.row().classes("items-center justify-between w-full"):
    with ui.row().classes("items-center gap-4"):
        ui.icon("schedule").classes("text-white/70")
        inp_hours = ui.number(label="Hours", value=0.5, min=0.05, max=24, step=0.05).classes(
            "w-[140px]"
        )
        sel_bucket = ui.select(
            {
                1: "1 s",
                2: "2 s",
                5: "5 s",
                10: "10 s",
                15: "15 s",
                30: "30 s",
                60: "60 s",
            },
            value=5,
            label="Bucket",
        ).classes("w-[140px]")

    # 명령 슬라이더 (Air Setpoint L/min)
    with ui.row().classes("items-center gap-3"):
        ui.label("Air Setpoint (L/min)").classes("text-white/70")
        air_set_slider = (
            ui.slider(min=160, max=210, step=0.5, value=190)
            .props("label color=teal")
            .classes("w-[300px]")
        )

        async def apply_air_setpoint(v: float) -> None:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(f"{API_BASE}/api/v1/commands/air_setpoint", json={"value": v})
                ui.notify(f"Air setpoint applied: {v:.1f} L/min", color="positive")
            except Exception as e:
                ui.notify(f"Air setpoint failed: {e}", color="negative")

        ui.button(
            "적용",
            on_click=lambda: asyncio.create_task(apply_air_setpoint(float(air_set_slider.value))),
        ).classes("ml-1")

    # 명령 슬라이더 (Pump Hz)
    with ui.row().classes("items-center gap-3"):
        ui.label("Pump Hz Setpoint (Hz)").classes("text-white/70")
        pump_hz_slider = (
            ui.slider(min=20, max=60, step=0.5, value=45)
            .props("label color=teal")
            .classes("w-[260px]")
        )

        async def apply_pump_hz(v: float) -> None:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"{API_BASE}/api/v1/commands/pump_hz_setpoint", json={"value": v}
                    )
                ui.notify(f"Pump Hz applied: {v:.1f} Hz", color="positive")
            except Exception as e:
                ui.notify(f"Pump Hz failed: {e}", color="negative")

        ui.button(
            "적용", on_click=lambda: asyncio.create_task(apply_pump_hz(float(pump_hz_slider.value)))
        ).classes("ml-1")

# =========================
# KPI CARDS (CLICK TO ZOOM)
# =========================
with ui.row().classes("gap-6"):
    card_do, v_do = metric_card("DO (mg/L)")
    card_mlss, v_mlss = metric_card("MLSS (mg/L)")
    card_temp, v_temp = metric_card("Temp (°C)")
    card_ph, v_ph = metric_card("pH")
    card_air, v_air = metric_card("Air Flow (L/min)")
    card_power, v_power = metric_card("Power (kW)")

# 단일 지표 확대 다이얼로그
single_metric_key: str | None = None
with ui.dialog() as single_dialog, ui.card().classes("w-[1000px] max-w-[95vw] bg-black/30"):
    single_title = ui.label("Metric").classes("text-white text-lg mb-2")
    trend_single: Any = ui.echart(
        {
            "backgroundColor": "transparent",
            "tooltip": {"trigger": "axis"},
            "grid": {"left": 50, "right": 30, "bottom": 40, "top": 30},
            "xAxis": {
                "type": "category",
                "data": [],
                "axisLine": {"lineStyle": {"color": "#888"}},
                "axisLabel": {"color": "#bbb"},
            },
            "yAxis": {
                "type": "value",
                "name": "",
                "axisLine": {"lineStyle": {"color": "#888"}},
                "axisLabel": {"color": "#bbb"},
            },
            "series": [{"name": "", "type": "line", "showSymbol": False, "data": []}],
        }
    ).classes("w-[960px] h-[420px]")
    ui.button("닫기", on_click=single_dialog.close).classes("mt-3")


def open_single_dialog(key: str) -> None:
    """단일 지표 확대 열기/제목/축 갱신"""
    global single_metric_key
    single_metric_key = key
    meta = next((m for m in METRICS if m["key"] == key), None)
    if meta:
        single_title.text = f'Realtime Trend · {meta["label"]}'
        trend_single.options["yAxis"]["name"] = meta["label"]
        trend_single.options["series"][0]["name"] = meta["label"]
    single_dialog.open()


# 카드 클릭 핸들러 연결
card_do.on("click", lambda e: open_single_dialog("DO"))
card_mlss.on("click", lambda e: open_single_dialog("MLSS"))
card_temp.on("click", lambda e: open_single_dialog("temp"))
card_ph.on("click", lambda e: open_single_dialog("pH"))
card_air.on("click", lambda e: open_single_dialog("air_flow"))
card_power.on("click", lambda e: open_single_dialog("power"))

# =========================
# MAIN TREND DIALOG (6-LINE)
# =========================
with ui.dialog() as trend_dialog, ui.card().classes("w-[1100px] max-w-[95vw] bg-black/30"):
    ui.label("Realtime Trend (DO, Air (L/min), MLSS, Temp, pH, Power)").classes(
        "text-white text-lg mb-2"
    )
    trend: Any = ui.echart(build_trend_options()).classes("w-[1040px] h-[460px]")
    ui.button("닫기", on_click=trend_dialog.close).classes("mt-3")

ui.button("트렌드 크게 보기", on_click=trend_dialog.open).classes("mt-2")


# =========================
# POLLING LOOP
# =========================
async def poll_loop():
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            # 1) 최신 KPI
            try:
                r = await client.get(f"{API_BASE}/api/v1/last")
                if r.status_code == 200 and r.json():
                    d = r.json()
                    v_do.text = f"{d.get('DO', 0):.2f}"
                    v_mlss.text = f"{d.get('MLSS', 0):.0f}"
                    v_temp.text = f"{d.get('temp', 0):.2f}"
                    v_ph.text = f"{d.get('pH', 0):.2f}"
                    v_air.text = f"{d.get('air_flow', 0):.1f}"
                    v_power.text = f"{d.get('power', 0):.2f}"
            except Exception as e:
                ui.notify(f"KPI fetch error: {e}", color="negative")

            # 2) 트렌드 데이터
            try:
                hrs = float(inp_hours.value or 0.5)
                bkt = int(sel_bucket.value or 5)
                fields = ",".join([m["key"] for m in METRICS])
                url = f"{API_BASE}/api/v1/trend?fields={fields}&hours={hrs}&bucket_sec={bkt}"
                r2 = await client.get(url)
                if r2.status_code == 200:
                    rows: list[dict[str, Any]] = r2.json() or []

                    # x축(시각 라벨)
                    def short_ts(s: Any) -> str:
                        s = str(s or "")
                        # 끝 8자리(HH:MM:SS)가 보통 시간 형태
                        return s[-8:] if len(s) >= 8 else s

                    xs = [short_ts(row.get("ts")) for row in rows]

                    # 메인 6라인 트렌드 채우기
                    trend.options["xAxis"]["data"] = xs
                    for i, meta in enumerate(METRICS):
                        trend.options["series"][i]["data"] = [row.get(meta["key"]) for row in rows]
                    await trend.update()

                    # 단일 지표 확대가 열려 있으면 함께 갱신
                    if single_metric_key:
                        meta = next((m for m in METRICS if m["key"] == single_metric_key), None)
                        if meta:
                            trend_single.options["xAxis"]["data"] = xs
                            trend_single.options["series"][0]["data"] = [
                                row.get(meta["key"]) for row in rows
                            ]
                            await trend_single.update()
            except Exception as e:
                ui.notify(f"Trend fetch error: {e}", color="negative")

            await asyncio.sleep(1.0)


# 첫 렌더 직후 폴링 시작
ui.timer(0.1, lambda: asyncio.create_task(poll_loop()), once=True)

# Pylance 경고 회피용 (ui.run 타입 추론 이슈)
cast(Any, ui).run(title="ESA HMI", host="127.0.0.1", port=8080)
