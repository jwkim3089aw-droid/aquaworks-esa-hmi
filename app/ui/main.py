# app/ui/main.py
from __future__ import annotations

from typing import Any, cast

from nicegui import ui  # [UNCHANGED]

from .charts import build_trend_options
from .commands import build_command_panel
from .components import metric_card
from .config import API_BASE, AXIS_POSITIONS, FONT_SCALES, METRICS
from .controls import build_top_controls
from .dialogs import create_full_trend_dialog, create_single_dialog
from .history import create_history_table
from .polling import start_polling

# === Theme ===
ui.dark_mode().enable()
ui.colors(primary="teal")

# === Root layout ===
root = ui.column().classes("w-full p-4 gap-4")
root.style(f"font-size: {FONT_SCALES['M']}px")

with root:
    # Top controls
    inp_hours, sel_bucket = build_top_controls(root, FONT_SCALES)

    # 2-column layout
    with ui.row().classes("items-start gap-6 w-full"):
        # Left column
        with ui.column().classes("w-[52%] min-w-[520px] gap-4"):
            # KPI grid (2x3)
            with ui.grid(columns=2).classes("gap-4"):
                card_do, v_do, s_do = metric_card("DO (mg/L)")
                card_mlss, v_mlss, s_mlss = metric_card("MLSS (mg/L)")
                card_temp, v_temp, s_temp = metric_card("Temp (°C)")
                card_ph, v_ph, s_ph = metric_card("pH")
                card_air, v_air, s_air = metric_card("Air Flow (L/min)")
                card_power, v_power, s_power = metric_card("Power (kW)")

            ui.label("Realtime Trend (6 metrics)").classes("text-white/80 text-sm")
            trend_embed: Any = ui.echart(build_trend_options(METRICS, AXIS_POSITIONS)).classes(
                "w-full h-[340px]"
            )

            # 큰 다이얼로그 열기 버튼
            def open_trend_dialog() -> None:
                trend_dialog.open()

            ui.button("트렌드 크게 보기", on_click=open_trend_dialog).classes("mt-1")

        # Right column
        with ui.column().classes("flex-1 min-w-[420px] gap-4"):
            add_cmd_history, tbl_history, history_rows = create_history_table()
            air_set_slider, pump_hz_slider = build_command_panel(API_BASE, add_cmd_history)

# Dialogs
single_dialog, trend_single, open_single_dialog, get_single_key = create_single_dialog(METRICS)
trend_dialog, trend_full = create_full_trend_dialog(METRICS, AXIS_POSITIONS)


# 카드 클릭 → 단일 지표 확대 (lambda의 알 수 없는 매개변수 타입 경고 제거)  # [ADDED]
def _make_open_handler(key: str):
    def _h(_: Any) -> None:
        open_single_dialog(key)

    return _h


card_do.on("click", _make_open_handler("DO"))
card_mlss.on("click", _make_open_handler("MLSS"))
card_temp.on("click", _make_open_handler("temp"))
card_ph.on("click", _make_open_handler("pH"))
card_air.on("click", _make_open_handler("air_flow"))
card_power.on("click", _make_open_handler("power"))

# 폴링 스타트
label_map: dict[str, Any] = {
    "DO": v_do,
    "MLSS": v_mlss,
    "temp": v_temp,
    "pH": v_ph,
    "air_flow": v_air,
    "power": v_power,
}
sparks: dict[str, Any] = {
    "DO": s_do,
    "MLSS": s_mlss,
    "temp": s_temp,
    "pH": s_ph,
    "air_flow": s_air,
    "power": s_power,
}
start_polling(
    api_base=API_BASE,
    metrics=METRICS,
    label_map=label_map,
    trend_embed=trend_embed,
    trend_full=trend_full,
    trend_single=trend_single,
    get_single_key=get_single_key,
    sparks=sparks,
    inp_hours=inp_hours,
    sel_bucket=sel_bucket,
)

# run
cast(Any, ui).run(title="ESA HMI", host="127.0.0.1", port=8080)
