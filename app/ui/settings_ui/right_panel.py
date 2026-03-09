# app/ui/settings_ui/right_panel.py
from typing import Dict, Any, Callable
from nicegui import ui
from app.ui.settings_ui.config import TAG_LIST, MB_TYPES
from app.models.settings import BackendType


def create_right_panel(
    switch_sim: ui.switch,
    backend_selector: ui.select,
    refs_mb_type: Dict[str, ui.select],
    refs_mb_addr: Dict[str, ui.number],
    refs_ua_node: Dict[str, ui.input],
    refs_src_icon: Dict[str, ui.button],
    open_dialog_fn: Callable[[str, str], None],
    ui_refs: Dict[str, Any],
):
    with ui.column().classes("col-span-9 h-full min-h-0 flex flex-col gap-0"):

        # 🌟 대기 화면 (기기를 선택하기 전)
        placeholder_card = ui.card().classes(
            "w-full h-full bg-[#0f172a] border border-slate-700 p-0 flex flex-col items-center justify-center shadow-xl rounded-lg transition-opacity duration-300"
        )
        with placeholder_card:
            ui.icon("ads_click", size="xl", color="slate-600").classes("mb-4 animate-bounce")
            ui.label("좌측 목록에서 기기를 선택해 주세요.").classes(
                "text-lg font-bold text-slate-400"
            )
            ui.label("새 기기를 추가 중이라면 팝업의 [설정 적용]을 먼저 눌러주세요.").classes(
                "text-sm text-slate-500 mt-2"
            )

        # 📊 데이터 매핑 테이블 (기기 선택 후 표시됨)
        table_card = ui.card().classes(
            "w-full h-full flex-1 bg-[#0f172a] border border-slate-700 p-0 flex flex-col shadow-xl overflow-hidden rounded-lg transition-opacity duration-300 hidden"
        )
        with table_card:
            with ui.row().classes(
                "w-full bg-slate-800 border-b border-slate-600 items-center text-xs font-bold text-slate-300 tracking-wider shrink-0"
            ):
                ui.label("데이터 이름 (태그)").classes(
                    "w-[25%] px-4 py-3 border-r border-slate-600"
                )

                with ui.row().classes("flex-1 items-center gap-0") as head_mb:
                    ui.label("데이터 타입").classes("w-[35%] px-4 py-3 border-r border-slate-600")
                    ui.label("메모리 주소").classes("flex-1 px-4 py-3")
                head_mb.bind_visibility_from(
                    backend_selector, "value", backward=lambda v: v == BackendType.MODBUS.value
                )

                with ui.row().classes("flex-1 items-center gap-0") as head_opc:
                    ui.label("노드 ID / 탐색 이름").classes("w-full px-4 py-3")
                head_opc.bind_visibility_from(
                    backend_selector, "value", backward=lambda v: v == BackendType.OPCUA.value
                )

                ui.label("").classes("w-[40px]")

            with ui.scroll_area().classes("w-full flex-1 bg-[#0f172a] p-0"):
                for i, tag in enumerate(TAG_LIST):
                    bg_cls = "bg-slate-800/20" if i % 2 == 0 else "bg-transparent"

                    with ui.row().classes(
                        f"w-full items-center {bg_cls} hover:bg-cyan-900/30 border-b border-slate-800 transition-colors group h-[44px]"
                    ):
                        with ui.row().classes(
                            "w-[25%] h-full items-center px-4 border-r border-slate-800"
                        ):
                            ui.label(tag["label"]).classes(
                                "text-sm font-bold text-cyan-50 group-hover:text-cyan-300 truncate transition-colors"
                            )

                        with ui.element("div").classes("flex-1 h-full relative"):
                            with ui.row().classes(
                                "w-full h-full items-center absolute top-0 left-0"
                            ) as row_mb:
                                sel = (
                                    ui.select(MB_TYPES, value=tag["def_type"])
                                    .props(
                                        "borderless dense options-dense behavior=menu input-class='text-sm text-slate-200'"
                                    )
                                    .classes(
                                        "w-[35%] px-3 border-r border-slate-800 h-full flex items-center"
                                    )
                                )
                                sel.bind_enabled_from(switch_sim, "value", backward=lambda x: not x)
                                refs_mb_type[tag["key"]] = sel

                                num = (
                                    ui.number(value=tag["def_addr"], format="%.0f")
                                    .props(
                                        "borderless dense input-class='font-mono text-sm text-slate-200'"
                                    )
                                    .classes("flex-1 px-3 h-full flex items-center")
                                )
                                num.bind_enabled_from(switch_sim, "value", backward=lambda x: not x)
                                refs_mb_addr[tag["key"]] = num

                            row_mb.bind_visibility_from(
                                backend_selector,
                                "value",
                                backward=lambda v: v == BackendType.MODBUS.value,
                            )

                            with ui.row().classes(
                                "w-full h-full items-center absolute top-0 left-0"
                            ) as row_opc:
                                txt = (
                                    ui.input(value=tag["def_ua"])
                                    .props(
                                        "borderless dense input-class='font-mono text-sm text-cyan-300' placeholder='ns=2;s=...'"
                                    )
                                    .classes("w-full px-3 h-full flex items-center")
                                )
                                txt.bind_enabled_from(switch_sim, "value", backward=lambda x: not x)
                                refs_ua_node[tag["key"]] = txt

                            row_opc.bind_visibility_from(
                                backend_selector,
                                "value",
                                backward=lambda v: v == BackendType.OPCUA.value,
                            )

                        with ui.row().classes("w-[40px] h-full items-center justify-center"):
                            btn = ui.button(
                                on_click=lambda e, k=tag["key"], l=tag["label"]: open_dialog_fn(
                                    k, l
                                )
                            )
                            btn.props("flat dense icon=settings_ethernet size=sm round").classes(
                                "text-slate-500 hover:text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                            )
                            refs_src_icon[tag["key"]] = btn

        # 안전하게 클래스로 끄고 켤 수 있도록 ui_refs에 저장
        ui_refs["right_placeholder"] = placeholder_card
        ui_refs["right_table"] = table_card
