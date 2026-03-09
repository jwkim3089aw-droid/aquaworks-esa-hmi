# app/ui/components/header.py
from nicegui import ui
from typing import Dict, Callable
from app.ui.history_dialog import create_history_dialog

# 🚀 [NEW] JSON 설정 파일 관리자 임포트
from app.core.device_config import load_device_configs


def create_header(current_rtu: Dict[str, int], on_rtu_change: Callable[[int], None]):
    """상단 헤더 생성 (기계 선택기 포함)"""
    history_dialog = create_history_dialog()

    # 🚀 [수정] 하드코딩 제거! JSON 파일에서 실제 기기 목록 읽어오기
    devices = load_device_configs()

    rtu_options = {}
    for dev in devices:
        # 파일에 이름이 없으면 Device-ID 형태로 표시
        name = dev.get("name", f"Device-{dev['id']}")
        rtu_options[dev["id"]] = name

    # 예외 처리: 등록된 기기가 하나도 없을 경우
    if not rtu_options:
        rtu_options = {0: "등록된 기기 없음"}
        current_val = 0
    else:
        # 현재 선택된 기기 ID가 JSON에 없으면(삭제되었으면) 첫 번째 기기로 자동 변경
        if current_rtu["id"] not in rtu_options:
            current_val = list(rtu_options.keys())[0]
        else:
            current_val = current_rtu["id"]

    with ui.row().classes("w-full max-w-[1400px] mx-auto justify-between items-center px-7 py-0"):
        with ui.row().classes("items-center gap-4"):
            ui.image("/static/images/logo.png").classes("w-30 h-8 object-contain")
            ui.label("ESA HMI").classes("text-lg font-semibold text-white")

            # 🚀 장비 선택 드롭다운 (동적 렌더링)
            dropdown = (
                ui.select(
                    options=rtu_options,
                    value=current_val,
                    on_change=lambda e: on_rtu_change(e.value) if e.value != 0 else None,
                )
                .props("dense outlined dark")
                .classes("w-48 ml-4 bg-gray-800 text-white rounded")
            )

            # 기기가 비어있으면 드롭다운 조작 막기
            if not devices:
                dropdown.disable()

        with ui.row().classes("top-controls items-center gap-2"):
            ui.button(icon="history", on_click=history_dialog.open).props(
                "flat round color=white"
            ).tooltip("History Data Analysis")
            ui.button(icon="settings", on_click=lambda: ui.navigate.to("/settings")).props(
                "flat round color=white"
            ).tooltip("Settings")
