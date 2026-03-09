# app/ui/theme.py
from __future__ import annotations
from nicegui import ui

def apply_theme() -> None:
    """대시보드 다크 테마 적용"""
    ui.colors(
        primary='#14B8A6',   # teal-500
        secondary='#1F2937', # gray-800
        accent='#22D3EE',    # cyan-400
        positive='#10B981',  # emerald-500
        negative='#EF4444',  # red-500
        info='#60A5FA',      # blue-400
        warning='#F59E0B',   # amber-500
    )
    ui.dark_mode().enable()
    ui.query('body').style('background:#0B1220')

    # 전역 보정
    ui.add_css("""
    /* 숫자 입력 가운데 정렬 */
    input[type="number"] { text-align:center; }
    /* 버튼 최소폭 강제 해제 (불필요한 넓이 방지) */
    .q-btn { min-width: auto !important; }
    """)