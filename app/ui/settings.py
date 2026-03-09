# app/ui/settings.py
from nicegui import ui
import asyncio
import time

from app.ui.settings_ui.layout import layout_frame
from app.models.settings import BackendType
from app.ui.settings_ui.header import create_header
from app.ui.settings_ui.left_panel import create_left_panel
from app.ui.settings_ui.right_panel import create_right_panel
from app.ui.settings_ui.dialog import SourceDialog

# 태그 매핑 리스트 불러오기
from app.ui.settings_ui.config import TAG_LIST

from app.workers.manager import worker_manager
from app.core.device_config import load_device_configs, save_device_configs, get_device_config

state = {
    "devices": [],
    "current_rtu_id": None,
    "backend_type": BackendType.MODBUS.value,
    "host": "127.0.0.1",
    "port": 502,
    "unit_id": 1,
    "ns": "",
    "custom_sources": {},
    "sim_mode": False,
}

refs_mb_type = {}
refs_mb_addr = {}
refs_ua_node = {}
refs_src_icon = {}
inputs_net = {}

ui_refs = {}
radio_backend_ref = None


async def load_devices():
    configs = load_device_configs()
    state["devices"] = []
    for c in configs:
        is_running = c["id"] in getattr(worker_manager, "_poller_tasks", {})
        state["devices"].append(
            {
                "id": c["id"],
                "name": c.get("name", f"기기 {c['id']}"),
                "protocol": c.get("protocol", BackendType.MODBUS.value),
                "host": c.get("host", "127.0.0.1"),
                "port": c.get("port", 502),
                "is_active": is_running,
            }
        )


def get_devices_sync():
    return state["devices"]


def _on_new_device_click():
    state["current_rtu_id"] = None
    state["backend_type"] = BackendType.MODBUS.value
    if radio_backend_ref:
        radio_backend_ref.value = BackendType.MODBUS.value

    if "name" in inputs_net:
        inputs_net["name"].value = ""
    if "host" in inputs_net:
        inputs_net["host"].value = "127.0.0.1"
    if "port" in inputs_net:
        inputs_net["port"].value = 502
    if "unit_id" in inputs_net:
        inputs_net["unit_id"].value = 1
    if "ns" in inputs_net:
        inputs_net["ns"].value = ""

    # 표를 리셋 (기본값으로 채움)
    for tag in TAG_LIST:
        k = tag["key"]
        if k in refs_mb_type:
            refs_mb_type[k].value = tag["def_type"]
        if k in refs_mb_addr:
            refs_mb_addr[k].value = tag["def_addr"]
        if k in refs_ua_node:
            refs_ua_node[k].value = tag["def_ua"]

    # 새 기기 모드: 대기 화면 표시
    if "right_placeholder" in ui_refs:
        ui_refs["right_placeholder"].classes(remove="hidden")
    if "right_table" in ui_refs:
        ui_refs["right_table"].classes(add="hidden")


def _on_device_select(rtu_data: dict, show_notify: bool = True):
    full_cfg = get_device_config(rtu_data["id"]) or {}

    state["current_rtu_id"] = rtu_data["id"]
    state["backend_type"] = full_cfg.get("protocol", BackendType.MODBUS.value)
    if radio_backend_ref:
        radio_backend_ref.value = state["backend_type"]

    if "name" in inputs_net:
        inputs_net["name"].value = full_cfg.get("name", f"기기 {rtu_data['id']}")
    if "host" in inputs_net:
        inputs_net["host"].value = full_cfg.get("host", "127.0.0.1")
    if "port" in inputs_net:
        inputs_net["port"].value = full_cfg.get("port", 502)
    if "unit_id" in inputs_net:
        inputs_net["unit_id"].value = full_cfg.get("unit_id", 1)
    if "ns" in inputs_net:
        inputs_net["ns"].value = full_cfg.get("ns", "")

    # JSON에 저장된 진짜 값을 읽어서 표에 뿌림
    saved_tags = full_cfg.get("tags", {})
    for tag in TAG_LIST:
        k = tag["key"]
        tag_data = saved_tags.get(k, {})
        if k in refs_mb_type:
            refs_mb_type[k].value = tag_data.get("mb_type", tag["def_type"])
        if k in refs_mb_addr:
            refs_mb_addr[k].value = tag_data.get("mb_addr", tag["def_addr"])
        if k in refs_ua_node:
            refs_ua_node[k].value = tag_data.get("ua_node", tag["def_ua"])

    # 기기 선택됨: 대기 화면 숨기고 매핑 표 노출!
    if "right_placeholder" in ui_refs:
        ui_refs["right_placeholder"].classes(add="hidden")
    if "right_table" in ui_refs:
        ui_refs["right_table"].classes(remove="hidden")

    if show_notify:
        name_val = inputs_net["name"].value if "name" in inputs_net else f"기기 {rtu_data['id']}"
        ui.notify(f"⚙️ [{name_val}] 매핑 정보 로드 완료", type="info", timeout=1200)


async def _on_device_delete(rtu_id: int):
    try:
        configs = load_device_configs()
        new_configs = [c for c in configs if c["id"] != rtu_id]
        save_device_configs(new_configs)

        await load_devices()
        if state["current_rtu_id"] == rtu_id:
            _on_new_device_click()
        if "refresh_device_list" in ui_refs:
            ui_refs["refresh_device_list"]()

        ui.notify("🗑️ 기기 삭제 완료", type="positive", timeout=1200)

        async def _bg_stop_worker():
            if hasattr(worker_manager, "remove_worker"):
                if asyncio.iscoroutinefunction(worker_manager.remove_worker):
                    await worker_manager.remove_worker(rtu_id)
                else:
                    worker_manager.remove_worker(rtu_id)
            elif hasattr(worker_manager, "stop_worker"):
                if asyncio.iscoroutinefunction(worker_manager.stop_worker):
                    await worker_manager.stop_worker(rtu_id)
                else:
                    worker_manager.stop_worker(rtu_id)

        asyncio.create_task(_bg_stop_worker())
    except Exception as e:
        ui.notify(f"기기 삭제 오류: {e}", type="negative", icon="error")


async def save_settings():
    try:
        new_name = (
            inputs_net["name"].value.strip()
            if "name" in inputs_net and inputs_net["name"].value
            else f"새 기기-{int(time.time())}"
        )
        new_backend = state["backend_type"]
        new_host = inputs_net["host"].value
        new_port = inputs_net["port"].value
        new_unit_id = inputs_net["unit_id"].value if "unit_id" in inputs_net else 1
        new_ns = inputs_net["ns"].value if "ns" in inputs_net else ""

        # 화면의 표에서 숫자들을 싹 긁어 모으기!
        tags_data = {}
        for tag in TAG_LIST:
            k = tag["key"]
            try:
                addr_val = int(refs_mb_addr[k].value)
            except (TypeError, ValueError):
                addr_val = tag["def_addr"]

            tags_data[k] = {
                "mb_type": refs_mb_type[k].value if k in refs_mb_type else tag["def_type"],
                "mb_addr": addr_val,
                "ua_node": refs_ua_node[k].value if k in refs_ua_node else tag["def_ua"],
            }

        configs = load_device_configs()
        target_id = state["current_rtu_id"]
        is_new = target_id is None

        if is_new:
            new_id = 1 if not configs else max(c["id"] for c in configs) + 1
            configs.append(
                {
                    "id": new_id,
                    "name": new_name,
                    "protocol": new_backend,
                    "host": str(new_host),
                    "port": int(new_port),
                    "unit_id": int(new_unit_id),
                    "ns": str(new_ns),
                    "tags": tags_data,  # JSON에 태그 데이터 영구 저장!
                }
            )
            save_device_configs(configs)
            state["current_rtu_id"] = new_id
            target_id = new_id
            ui.notify(f"✅ [{new_name}] 추가 완료!", type="positive", timeout=1200)

            _on_device_select({"id": target_id}, show_notify=False)
        else:
            for c in configs:
                if c["id"] == target_id:
                    c["name"], c["protocol"] = new_name, new_backend
                    c["host"], c["port"] = str(new_host), int(new_port)
                    c["unit_id"], c["ns"] = int(new_unit_id), str(new_ns)
                    c["tags"] = tags_data
                    break
            save_device_configs(configs)
            ui.notify(
                "✅ 설정 및 매핑 적용 완료!", type="positive", icon="check_circle", timeout=1200
            )

        await load_devices()
        if "refresh_device_list" in ui_refs:
            ui_refs["refresh_device_list"]()

        async def _bg_update_worker():
            if is_new:
                if hasattr(worker_manager, "add_worker"):
                    if asyncio.iscoroutinefunction(worker_manager.add_worker):
                        await worker_manager.add_worker(target_id)
                    else:
                        worker_manager.add_worker(target_id)
            else:
                if hasattr(worker_manager, "update_worker"):
                    if asyncio.iscoroutinefunction(worker_manager.update_worker):
                        await worker_manager.update_worker(target_id)
                    else:
                        worker_manager.update_worker(target_id)

        asyncio.create_task(_bg_update_worker())

    except Exception as e:
        ui.notify(f"설정 적용 실패: {e}", type="negative", icon="error")


def _on_backend_change(e):
    state["backend_type"] = e.value


def _on_sim_toggle(e):
    state["sim_mode"] = e.value


def _on_dlg_close(key: str):
    btn = refs_src_icon.get(key)
    if btn:
        cfg = state["custom_sources"].get(key, {})
        is_active = cfg.get("enabled", False)
        color = "cyan" if is_active else "slate-500"
        btn.classes(
            remove="text-slate-500 text-cyan-400",
            add=f"text-{color}-400" if is_active else "text-slate-500",
        )


@ui.page("/settings")
async def settings_page():
    global radio_backend_ref
    await load_devices()

    with layout_frame("기기 및 통신 설정"):
        dlg = SourceDialog(state, _on_dlg_close)
        create_header(save_settings, lambda: ui.navigate.to("/"))

        with ui.grid().classes("w-full flex-1 grid-cols-12 gap-6 p-4 min-h-0"):

            radio_backend, switch_sim, _, _ = create_left_panel(
                inputs_net=inputs_net,
                on_backend_change=_on_backend_change,
                on_sim_toggle=_on_sim_toggle,
                get_devices_fn=get_devices_sync,
                on_device_select=_on_device_select,
                on_new_device_click=_on_new_device_click,
                on_device_delete=_on_device_delete,
                on_device_save=save_settings,
                ui_refs=ui_refs,
            )
            radio_backend_ref = radio_backend

            create_right_panel(
                switch_sim,
                radio_backend,
                refs_mb_type,
                refs_mb_addr,
                refs_ua_node,
                refs_src_icon,
                dlg.open_for,
                ui_refs=ui_refs,
            )

            # 무조건 대기 화면(Placeholder)으로 얌전하게 시작
            _on_new_device_click()

    _on_backend_change(type("E", (object,), {"value": state["backend_type"]})())
