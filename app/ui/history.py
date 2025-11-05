# app/ui/history.py
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from nicegui import ui


def create_history_table() -> (
    tuple[Callable[[str, str, bool, str], None], Any, list[dict[str, Any]]]
):
    columns = [
        {"name": "ts", "label": "Time", "field": "ts"},
        {"name": "cmd", "label": "Command", "field": "cmd"},
        {"name": "value", "label": "Value", "field": "value"},
        {"name": "ok", "label": "OK", "field": "ok"},
        {"name": "msg", "label": "Message", "field": "msg"},
    ]
    rows: list[dict[str, Any]] = []
    table = ui.table(columns=columns, rows=rows).classes("w-full")

    # [CHANGED] create_task 없이 바로 업데이트
    def add_cmd_history(cmd: str, value: str, ok: bool, msg: str) -> None:
        nonlocal rows, table
        rows.insert(
            0,
            {
                "ts": datetime.now().strftime("%H:%M:%S"),
                "cmd": cmd,
                "value": value,
                "ok": "✔" if ok else "✖",
                "msg": msg,
            },
        )
        if len(rows) > 10:
            rows = rows[:10]
        table.rows = rows
        table.update()  # [CHANGED] 즉시 반영

    return add_cmd_history, table, rows
