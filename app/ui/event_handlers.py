# app/ui/event_handlers.py
# [CHANGED] 람다 → 명시 함수로 변경 (Pylance reportUnknownLambdaType 제거)
from __future__ import annotations
from typing import Callable, Any

def bind_click_events(card: Any, unit: str, open_single_dialog: Callable[[str], None]) -> None:
    def _on_click(_: Any) -> None:  # [ADDED] 명시적 파라미터 타입
        open_single_dialog(unit)
    card.on('click', _on_click)
