# app/ui/main.py
from __future__ import annotations

from typing import Any, cast

from nicegui import ui

from app.ui.charts import build_trend_options
from app.ui.commands import build_command_panel
from app.ui.components import metric_card
from app.ui.config import API_BASE, AXIS_POSITIONS, FONT_SCALES, METRICS, THEME
from app.ui.controls import build_top_controls
from app.ui.dialogs import create_full_trend_dialog, create_single_dialog
from app.ui.history import create_history_table
from app.ui.polling import start_polling
from app.ui.theme import apply_theme

# === Theme ===
apply_theme(THEME)  # [ADDED]

# === Root Layout ===
root = ui.column().classes("w-full p-4 gap-4")
root.style(f"font-size: {FONT_SCALES['M']}px")

with root:
    # Top Bar
    inp_hours, sel_bucket = build_top_controls(root, FONT_SCALES)

    # Main Grid (Left KPIs & Chart / Right Commands+History)
    with ui.row().classes("items-start gap-6 w-full"):
        with ui.column().classes("w-[58%] min-w-[560px] gap-4"):
            # KPI Grid
            with ui.grid(columns=3).classes("gap-4"):
                card_do, v_do, s_do = metric_card("DO (mg/L)")
                card_mlss, v_mlss, s_mlss = metric_card("MLSS (mg/L)")
                card_temp, v_temp, s_temp = metric_card("Temp (°C)")
                card_ph, v_ph, s_ph = metric_card("pH")
                card_air, v_air, s_air = metric_card("Air Flow (L/min)")
                card_power, v_power, s_power = metric_card("Power (kW)")

            # Trend Panel
            with ui.card().classes("aw-panel p-4"):
                ui.label("Realtime Trend (6 metrics)").classes("aw-section-title")
                trend_embed: Any = ui.echart(build_trend_options(METRICS, AXIS_POSITIONS)).classes(
                    "w-full h-[360px]"
                )
                ui.button("트렌드 크게 보기", on_click=lambda: trend_dialog.open()).classes(
                    "aw-btn mt-2"
                )

        with ui.column().classes("flex-1 min-w-[420px] gap-4"):
            add_cmd_history, tbl_history, history_rows = create_history_table()
            air_set_slider, pump_hz_slider = build_command_panel(API_BASE, add_cmd_history)

# Dialogs
single_dialog, trend_single, open_single_dialog, get_single_key = create_single_dialog(METRICS)
trend_dialog, trend_full = create_full_trend_dialog(METRICS, AXIS_POSITIONS)


# Card click → Single metric
def _handler(key: str):
    def _h(_: Any) -> None:
        open_single_dialog(key)

    return _h


card_do.on("click", _handler("DO"))
card_mlss.on("click", _handler("MLSS"))
card_temp.on("click", _handler("temp"))
card_ph.on("click", _handler("pH"))
card_air.on("click", _handler("air_flow"))
card_power.on("click", _handler("power"))

# Polling
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

cast(Any, ui).run(title="ESA HMI", host="127.0.0.1", port=8080)
