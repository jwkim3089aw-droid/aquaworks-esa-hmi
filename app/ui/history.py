# app/ui/history.py
from __future__ import annotations
from typing import List, Dict, Any
from nicegui import ui
from datetime import datetime

HISTORY_COLUMNS = [
    {"name": "time", "label": "Time", "field": "time", "align": "left"},
    {"name": "cmd", "label": "Command", "field": "cmd", "align": "left"},
    {"name": "value", "label": "Value", "field": "value", "align": "right"},
    {"name": "ok", "label": "OK", "field": "ok", "align": "center"},
    {"name": "msg", "label": "Message", "field": "msg", "align": "left"},
]


def make_history_card():
    card = ui.card().classes("w-[720px] bg-[#0F172A] rounded-xl shadow-lg border border-[#1F2937]")
    with card:
        table = (
            ui.table(columns=HISTORY_COLUMNS, rows=[], row_key="time")
            .props("dense flat bordered")
            .classes("w-full text-[#E5E7EB]")
        )
    return card, table


def add_rows(table: Any, rows: List[Dict[str, Any]]) -> None:
    table.rows += rows
    table.update()


def add_history(table: Any, cmd: str, value: str, ok: bool = True, msg: str = "OK") -> None:
    add_rows(
        table,
        [
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "cmd": cmd,
                "value": value,
                "ok": "Y" if ok else "N",
                "msg": msg,
            }
        ],
    )
