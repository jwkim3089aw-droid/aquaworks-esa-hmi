# app/ui/components/marks.py
from typing import List, Dict, Any, Optional
from nicegui import ui
from app.ui.common import metric_name_and_unit, title_of, format_mark_value


def create_marks_section(
    trend_marks: List[Dict[str, Any]],
    metrics: List[Dict[str, Any]],
    metric_keys: List[str],
    series_colors_by_key: Dict[str, str],
) -> Any:  # Returns render_trend_marks function

    trend_marks_container: Any = None

    def render_trend_marks() -> None:
        if trend_marks_container is None:
            return
        trend_marks_container.clear()

        if not trend_marks:
            with trend_marks_container:
                ui.label("차트에서 포인트를 클릭하면 여기 Trend Mark가 표시됩니다.").classes(
                    "text-xs text-[#6B7280] px-3 py-0"
                )
            return

        num_marks = len(trend_marks)
        col_width = "70px"
        BG_COLOR = "#0F172A"
        BORDER_COLOR = "#1F2937"
        STYLE_LEFT = f"position: sticky; left: 0; z-index: 20; background-color: {BG_COLOR}; border-right: 1px solid {BORDER_COLOR};"
        STYLE_BOTTOM = f"position: sticky; bottom: 0; z-index: 20; background-color: {BG_COLOR}; border-top: 1px solid {BORDER_COLOR};"
        STYLE_CORNER = f"position: sticky; left: 0; bottom: 0; z-index: 30; background-color: {BG_COLOR}; border-right: 1px solid {BORDER_COLOR}; border-top: 1px solid {BORDER_COLOR};"

        with trend_marks_container:
            grid = ui.element("div").style(
                f"display:grid; grid-template-columns: 67px repeat({num_marks}, {col_width}); grid-auto-rows: 26px; gap:0px;"
            )
            with grid:
                for key in metric_keys:
                    found = next((m for m in metrics if str(m.get("key", title_of(m))) == key), {})
                    base, _ = metric_name_and_unit(found)
                    row_color = series_colors_by_key.get(key, "#9CA3AF")
                    ui.label(base).style(f"color: {row_color}; {STYLE_LEFT}").classes(
                        "px-2 text-right text-xs flex items-center justify-end h-full font-bold"
                    )
                    for mark in trend_marks:
                        v = mark["values"].get(key)
                        ui.label(format_mark_value(key, v)).classes(
                            "px-0 text-right text-xs text-[#E5E7EB] font-mono flex items-center justify-end h-full"
                        )

                ui.label("Time").style(STYLE_CORNER).classes(
                    "px-2 text-right text-xs text-[#9CA3AF] flex items-center justify-end h-full font-bold"
                )
                for mark in trend_marks:
                    ui.label(mark["ts_label"]).style(STYLE_BOTTOM).classes(
                        "px-0 text-right text-xs text-[#E5E7EB] flex items-center justify-end h-full"
                    )

    with ui.card().classes(
        "w-full h-[260px] min-w-0 overflow-hidden bg-[#0F172A] rounded-xl shadow-lg border border-[#1F2937] flex flex-col pt-1 gap-0"
    ):
        with ui.row().classes("w-full items-center justify-between px-3 py-0 bg-[#111827]"):
            ui.label("Trend Marks").classes("text-sm font-bold text-[#E5E7EB]")
            ui.button(
                icon="delete", on_click=lambda: (trend_marks.clear(), render_trend_marks())
            ).props("round flat dense size=sm color=grey").tooltip("목록 초기화")

        trend_marks_container = ui.element("div").classes(
            "w-full flex-1 overflow-auto pt-0 custom-scrollbar"
        )

    return render_trend_marks
