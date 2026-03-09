# app/ui/settings_ui/left_panel.py
import asyncio
from typing import Dict, Any, Callable, Tuple, List
from nicegui import ui
from app.models.settings import BackendType
from app.ui.settings_ui.config import SIM_OPCUA_HOST, SIM_OPCUA_PORT, SIM_OPCUA_NS
from app.workers.ai_state import get_ai_state


def create_left_panel(
    inputs_net: Dict[str, Any],
    on_backend_change: Callable,
    on_sim_toggle: Callable,
    get_devices_fn: Callable[[], List[Dict]],
    on_device_select: Callable[[Dict], None],
    on_new_device_click: Callable[[], None],
    on_device_delete: Callable[[int], None],
    on_device_save: Callable[[], Any],
    ui_refs: Dict[str, Any],
) -> Tuple[ui.select, ui.switch, Any, Any]:

    saved_real_config = {"host": "", "port": 502, "ns": ""}
    device_icons: Dict[int, Any] = {}

    # ==========================================
    # 🌟 0. 프론트엔드 충돌 방지용 가상 상태 저장소 (Hidden State)
    # 팝업이 닫혀있어도 우측 패널이 안전하게 참조할 수 있도록 메인 DOM에 생성
    # ==========================================
    main_sim_state = ui.switch(value=False).classes("hidden")
    main_backend_state = ui.select(
        {e.value: e.value for e in BackendType}, value=BackendType.MODBUS.value
    ).classes("hidden")

    # ==========================================
    # 🌟 1. 설정 팝업 (Dialog) UI 정의
    # ==========================================
    with (
        ui.dialog() as config_dialog,
        ui.card().classes(
            "bg-[#0f172a] border border-slate-700 shadow-2xl p-6 w-[420px] flex flex-col gap-4"
        ),
    ):
        dialog_title = ui.label("✨ 새 기기 추가").classes("text-lg font-bold text-cyan-400 mb-2")

        sim_row = ui.row().classes(
            "w-full items-center justify-between px-3 py-2 rounded border transition-colors duration-300 bg-slate-800/50 border-slate-700/50"
        )
        with sim_row:
            sim_title = ui.label("🧪 가상 시뮬레이션 모드").classes(
                "text-xs font-bold transition-colors duration-300 text-slate-400"
            )
            with ui.row().classes("items-center gap-2"):
                sim_status_label = ui.label("OFF").classes(
                    "text-[11px] font-bold text-slate-500 w-[24px] text-right"
                )
                # 🚀 팝업 내부 스위치를 가상 스위치와 양방향 연동(bind_value)
                switch_sim = (
                    ui.switch()
                    .props("dense color=green size=sm")
                    .bind_value(main_sim_state, "value")
                )

        with ui.column().classes("w-full gap-1"):
            ui.label("통신 프로토콜 (Protocol)").classes("text-[10px] text-slate-400 font-bold")
            # 🚀 팝업 내부 프로토콜을 가상 프로토콜과 양방향 연동(bind_value)
            radio_backend = (
                ui.select(
                    {e.value: e.name.replace("_", " ") for e in BackendType},
                    value=BackendType.MODBUS.value,
                )
                .props(
                    "outlined dense options-dense behavior=menu input-class='font-bold text-sm text-cyan-50'"
                )
                .classes("w-full")
                .bind_value(main_backend_state, "value")
            )

        ui.separator().classes("bg-slate-700/50 my-1")

        with ui.column().classes("w-full gap-1"):
            ui.label("기기 이름 (식별자)").classes("text-[10px] text-slate-400 font-bold")
            inputs_net["name"] = (
                ui.input(placeholder="예: 메인 펌프")
                .props("outlined dense input-class='font-bold text-cyan-300 text-sm'")
                .classes("w-full")
            )

        with ui.column().classes("w-full gap-1"):
            ui.label("호스트 주소 (Target IP)").classes("text-[10px] text-slate-400 font-bold")
            inputs_net["host"] = (
                ui.input(placeholder="127.0.0.1")
                .props("outlined dense input-class='font-mono text-sm text-slate-200'")
                .classes("w-full")
            )
            inputs_net["host"].bind_enabled_from(main_sim_state, "value", backward=lambda x: not x)

        with ui.column().classes("w-full gap-1"):
            ui.label("통신 포트 (Port)").classes("text-[10px] text-slate-400 font-bold")
            inputs_net["port"] = (
                ui.number(placeholder="502", format="%.0f")
                .props("outlined dense input-class='font-mono text-sm text-slate-200'")
                .classes("w-full")
            )
            inputs_net["port"].bind_enabled_from(main_sim_state, "value", backward=lambda x: not x)

        cont_modbus = ui.column().classes("w-full gap-1 transition-all")
        cont_modbus.bind_visibility_from(
            main_backend_state, "value", backward=lambda v: v == BackendType.MODBUS.value
        )
        with cont_modbus:
            ui.label("슬레이브 ID (Unit ID)").classes("text-[10px] text-slate-400 font-bold mt-1")
            inputs_net["unit_id"] = (
                ui.number(placeholder="1", format="%.0f")
                .props("outlined dense input-class='font-mono text-sm text-slate-200'")
                .classes("w-full")
            )
            inputs_net["unit_id"].bind_enabled_from(
                main_sim_state, "value", backward=lambda x: not x
            )

        cont_opc = ui.column().classes("w-full gap-1 transition-all")
        cont_opc.bind_visibility_from(
            main_backend_state, "value", backward=lambda v: v == BackendType.OPCUA.value
        )
        with cont_opc:
            ui.label("네임스페이스 (Namespace URI)").classes(
                "text-[10px] text-slate-400 font-bold mt-1"
            )
            inputs_net["ns"] = (
                ui.input(placeholder="urn:example:server")
                .props("outlined dense input-class='font-mono text-sm text-slate-200'")
                .classes("w-full")
            )
            inputs_net["ns"].bind_enabled_from(main_sim_state, "value", backward=lambda x: not x)

        async def test_connection():
            host = inputs_net["host"].value
            try:
                port = int(inputs_net["port"].value)
            except:
                ui.notify(
                    "포트 번호가 올바르지 않습니다.", type="negative", icon="warning", timeout=1200
                )
                return

            ui.notify(f"📡 {host}:{port} 통신 연결 시도 중...", type="info", timeout=1200)
            try:
                future = asyncio.open_connection(host, port)
                reader, writer = await asyncio.wait_for(future, timeout=2.0)
                writer.close()
                await writer.wait_closed()
                ui.notify(
                    "🟢 통신 정상 (Ping 확인됨)", type="positive", icon="check_circle", timeout=1500
                )
            except Exception as e:
                ui.notify(f"🔴 연결 실패 (응답 없음)", type="negative", icon="error", timeout=1500)

        with ui.row().classes(
            "w-full items-center justify-between mt-4 pt-4 border-t border-slate-700"
        ):
            ui.button("통신 테스트", on_click=test_connection).props(
                "outline color=cyan size=sm"
            ).classes("font-bold bg-cyan-900/10 hover:bg-cyan-900/40")
            with ui.row().classes("gap-2"):
                ui.button("취소", on_click=config_dialog.close).props(
                    "outline color=slate-400 size=sm"
                ).classes("font-bold")

                async def _save_and_close():
                    await on_device_save()
                    config_dialog.close()

                ui.button("설정 적용", on_click=_save_and_close).props(
                    "color=cyan size=sm"
                ).classes("font-bold text-slate-900")

    # ==========================================
    # 🖱️ 2. 이벤트 핸들러 및 바인딩
    # ==========================================
    main_backend_state.on_value_change(on_backend_change)

    def handle_sim_toggle(e):
        is_sim_mode = e.value
        ns_comp = inputs_net.get("ns")
        if is_sim_mode:
            sim_status_label.set_text("ON")
            sim_status_label.classes(
                replace="text-[11px] font-bold text-green-400 w-[24px] text-right"
            )
            sim_title.classes(remove="text-slate-400", add="text-green-400")
            sim_row.classes(
                remove="bg-slate-800/50 border-slate-700/50",
                add="bg-green-900/20 border-green-800/50",
            )

            saved_real_config["host"] = inputs_net["host"].value
            saved_real_config["port"] = inputs_net["port"].value
            saved_real_config["ns"] = ns_comp.value if ns_comp else ""
            inputs_net["host"].value = SIM_OPCUA_HOST
            inputs_net["port"].value = SIM_OPCUA_PORT
            if ns_comp:
                ns_comp.value = SIM_OPCUA_NS
            ui.notify("시뮬레이션 모드 ON", type="positive", icon="science", timeout=1200)
        else:
            sim_status_label.set_text("OFF")
            sim_status_label.classes(
                replace="text-[11px] font-bold text-slate-500 w-[24px] text-right"
            )
            sim_title.classes(remove="text-green-400", add="text-slate-400")
            sim_row.classes(
                remove="bg-green-900/20 border-green-800/50",
                add="bg-slate-800/50 border-slate-700/50",
            )

            if saved_real_config["host"]:
                inputs_net["host"].value = saved_real_config["host"]
            if saved_real_config["port"]:
                inputs_net["port"].value = saved_real_config["port"]
            if ns_comp and saved_real_config["ns"]:
                ns_comp.value = saved_real_config["ns"]

        on_sim_toggle(e)

    main_sim_state.on_value_change(handle_sim_toggle)

    def handle_add_click():
        on_new_device_click()
        dialog_title.set_text("✨ 새 기기 추가")
        config_dialog.open()

    def handle_edit_click(rtu_data):
        on_device_select(rtu_data, show_notify=True)
        dialog_title.set_text(f"⚙️ '{rtu_data.get('name', f'기기 {rtu_data['id']}')}' 설정 수정")
        config_dialog.open()

    def confirm_and_delete(rtu_data):
        with (
            ui.dialog() as dialog,
            ui.card().classes("bg-[#0f172a] border border-slate-700 shadow-2xl p-5 w-[350px]"),
        ):
            with ui.row().classes("items-center gap-3 mb-2"):
                ui.icon("warning", color="red-400", size="md")
                ui.label(f"'{rtu_data.get('name', f'기기 {rtu_data['id']}')}' 삭제").classes(
                    "text-lg font-bold text-slate-200"
                )
            ui.label("이 기기를 정말 삭제하시겠습니까?").classes("text-sm text-slate-400 mb-6")
            with ui.row().classes("w-full justify-end gap-3"):
                ui.button("취소", on_click=dialog.close).props(
                    "outline color=slate-400 size=sm"
                ).classes("font-bold")

                async def do_delete():
                    dialog.close()
                    await on_device_delete(rtu_data["id"])

                ui.button("삭제하기", on_click=do_delete).props("color=red-500 size=sm").classes(
                    "font-bold text-white"
                )
        dialog.open()

    # ==========================================
    # 📱 3. 메인 왼쪽 패널 레이아웃 (오직 기기 목록만!)
    # ==========================================
    with ui.column().classes("col-span-3 h-full flex flex-col gap-0 min-h-0"):
        with ui.card().classes(
            "w-full flex-1 bg-[#0f172a] border border-slate-700 p-0 shadow-lg flex flex-col rounded-lg overflow-hidden"
        ):
            with ui.row().classes(
                "w-full bg-slate-800 border-b border-slate-600 px-3 py-3 items-center justify-between shrink-0"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("dns", color="cyan-400", size="sm")
                    ui.label("등록된 기기 목록").classes(
                        "text-sm font-bold text-slate-200 tracking-wider"
                    )
                ui.button(on_click=handle_add_click).props(
                    "flat dense icon=add color=cyan size=sm rounded"
                ).tooltip("새 기기 추가").classes("bg-cyan-900/30 hover:bg-cyan-800/50")

            device_list_container = ui.column().classes("w-full p-2 gap-1 flex-1 overflow-y-auto")

            def refresh_device_list():
                device_list_container.clear()
                device_icons.clear()
                devices = get_devices_fn()

                if not devices:
                    with device_list_container:
                        ui.label("등록된 기기가 없습니다.").classes(
                            "text-xs text-slate-500 italic p-3 text-center w-full"
                        )
                    return

                with device_list_container:
                    for d in devices:
                        rtu_id = d["id"]
                        with ui.row().classes(
                            "w-full items-center justify-between p-0 bg-slate-800/30 hover:bg-cyan-900/20 border border-transparent hover:border-cyan-800/50 rounded transition-colors group flex-nowrap"
                        ):

                            with (
                                ui.button(
                                    on_click=lambda rtu_data=d: on_device_select(
                                        rtu_data, show_notify=False
                                    )
                                )
                                .classes(
                                    "flex-1 justify-start items-center p-3 bg-transparent m-0 min-w-0"
                                )
                                .props("flat no-caps")
                            ):
                                icon = ui.icon("memory", size="xs", color="slate-500").classes(
                                    "group-hover:text-cyan-400 transition-colors shrink-0"
                                )
                                device_icons[rtu_id] = icon
                                ui.label(d.get("name", f"기기 {rtu_id}")).classes(
                                    "text-sm font-bold text-slate-300 ml-3 group-hover:text-white transition-colors truncate"
                                )

                            with ui.row().classes(
                                "items-center gap-0 opacity-0 group-hover:opacity-100 transition-opacity pr-2"
                            ):
                                ui.button(
                                    on_click=lambda rtu_data=d: handle_edit_click(rtu_data)
                                ).props("flat dense icon=settings size=sm").classes(
                                    "text-slate-400 hover:text-cyan-400 p-2"
                                ).tooltip(
                                    "통신 설정 수정"
                                )
                                ui.button(
                                    on_click=lambda rtu_data=d: confirm_and_delete(rtu_data)
                                ).props("flat dense icon=delete size=sm").classes(
                                    "text-red-400 hover:text-red-300 p-2"
                                ).tooltip(
                                    "기기 삭제"
                                )

            ui_refs["refresh_device_list"] = refresh_device_list
            refresh_device_list()

            def _health_check_tick():
                for r_id, icon_obj in device_icons.items():
                    state = get_ai_state(r_id)
                    if getattr(state, "fatal", False):
                        icon_obj.props("color=red-500 name=error")
                    elif getattr(state, "running", False):
                        icon_obj.props("color=green-400 name=memory")
                    else:
                        icon_obj.props("color=slate-500 name=memory")

            ui.timer(1.0, _health_check_tick)

    # 🚀 팝업 내부의 변수가 아닌 안전한 가상 스위치를 넘겨줍니다!
    return main_backend_state, main_sim_state, None, None
