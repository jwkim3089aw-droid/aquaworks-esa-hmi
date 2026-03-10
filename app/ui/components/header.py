# app/ui/components/header.py
from nicegui import ui
from typing import Dict, Callable
from app.ui.history_dialog import create_history_dialog

# JSON 설정 파일 관리자 임포트
from app.core.device_config import load_device_configs


def create_header(current_rtu: Dict[str, int], on_rtu_change: Callable[[int], None]):
    """상단 헤더 생성 (기계 선택기 포함)"""
    history_dialog = create_history_dialog()

    # 하드코딩 제거! JSON 파일에서 실제 기기 목록 읽어오기
    devices = load_device_configs()

    # 🎯 메뉴판 맨 위에 '0번: 통합 관제 센터'를 고정으로 박아둡니다!
    rtu_options = {0: "🌐 통합 관제 센터 (Overview)"}

    for dev in devices:
        # 파일에 이름이 없으면 Device-ID 형태로 표시
        name = dev.get("name", f"Device-{dev['id']}")
        rtu_options[dev["id"]] = name

    # 예외 처리: 등록된 기기가 하나도 없을 경우
    if len(rtu_options) == 1:
        rtu_options = {0: "등록된 기기 없음"}
        if current_rtu["id"] not in rtu_options:
            current_rtu["id"] = 0

    with ui.row().classes("w-full max-w-[1400px] mx-auto justify-between items-center px-7 py-0"):
        with ui.row().classes("items-center gap-4"):

            # 🎯 [핵심 패치 1] 로고 영역을 클릭 가능하게 만들고, 누르면 0번(통합 관제)으로 이동!
            with (
                ui.row()
                .classes("items-center gap-4 cursor-pointer hover:opacity-80 transition-opacity")
                .on("click", lambda: on_rtu_change(0))
            ):
                ui.image("/static/images/logo.png").classes(
                    "w-30 h-8 object-contain pointer-events-none"
                )
                ui.label("ESA HMI").classes("text-lg font-semibold text-white select-none")

            # 🎯 [핵심 패치 2] bind_value를 추가하여 타일을 클릭해서 넘어와도 드롭다운 텍스트가 알아서 바뀜!
            dropdown = (
                ui.select(
                    options=rtu_options,
                    value=current_rtu.get("id", 0),
                    on_change=lambda e: on_rtu_change(e.value),
                )
                .bind_value(current_rtu, "id")  # <-- 이 녀석이 내부 변수와 UI를 찰떡같이 묶어줍니다
                .props("dense outlined dark")
                .classes("w-60 ml-4 bg-gray-800 text-white rounded font-bold")
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
