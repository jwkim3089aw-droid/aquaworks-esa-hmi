# app/ui/settings_ui/header.py
import asyncio
from nicegui import ui
from typing import Callable


def create_header(on_save: Callable, on_exit: Callable):

    # 🚀 핵심: 저장 후 종료까지 한 번에 처리하는 콤보 함수
    async def handle_save_and_exit():
        try:
            # 1. 저장 로직 실행 (async 여부 확인 후 안전하게 실행)
            if asyncio.iscoroutinefunction(on_save):
                await on_save()
            else:
                on_save()

            # 2. UX 향상: 성공 알림 띄우기
            ui.notify("Settings applied successfully!", type="positive", position="top-right")

            # 3. 0.5초 대기 (알림창을 볼 수 있는 약간의 여유)
            await asyncio.sleep(0.5)

            # 4. 원래 화면으로 복귀 (EXIT 버튼과 동일한 로직 실행)
            if asyncio.iscoroutinefunction(on_exit):
                await on_exit()
            else:
                on_exit()

        except Exception as e:
            # 에러 발생 시 원래 화면으로 튕기지 않고 에러 메시지 표시
            ui.notify(f"Failed to save: {e}", type="negative", position="top-right")

    with ui.row().classes(
        "w-full items-center justify-between py-2 border-b border-slate-700 mb-2"
    ):
        with ui.row().classes("items-center gap-3"):
            ui.icon("settings_applications", size="md", color="cyan-400")
            ui.label("SYSTEM CONFIGURATION").classes(
                "text-xl font-black text-white tracking-widest"
            )
            ui.label("|").classes("text-slate-600 mx-1")
            ui.label("Connection & Data Mapping").classes("text-sm text-slate-400 font-mono pt-1")

        with ui.row().classes("items-center gap-2"):
            # 기존 EXIT 버튼은 그대로 유지
            ui.button("EXIT", on_click=on_exit).props(
                "flat dense color=grey text-color=grey-4 no-caps"
            )

            # 🚀 클릭 이벤트를 on_save에서 handle_save_and_exit 콤보 함수로 변경!
            ui.button("APPLY CHANGES", on_click=handle_save_and_exit).props(
                "unelevated dense color=cyan-7 text-color=white icon=save no-caps"
            ).classes("px-4 font-bold")
