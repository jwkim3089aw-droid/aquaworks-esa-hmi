# app/ui/settings_ui/layout.py
from contextlib import contextmanager
from nicegui import ui


@contextmanager
def layout_frame(page_title: str):
    """
    [Settings 전용 레이아웃]
    화면 크기를 브라우저 창 높이(h-screen)로 고정하고,
    넘치는 부분은 숨겨서(overflow: hidden) 메인 스크롤바를 없앱니다.
    """
    ui.page_title(page_title)

    # [수정] body 자체의 스크롤도 방지 (overflow: hidden 추가)
    ui.query("body").style("background-color: #0B1120; margin: 0; padding: 0; overflow: hidden;")

    # [수정] min-h-screen -> h-screen (높이 고정)
    # [수정] overflow-hidden 추가 (내부 요소가 튀어나오면 자름)
    with ui.column().classes("w-full h-screen bg-[#0B1120] text-slate-200 gap-0 overflow-hidden"):
        yield
