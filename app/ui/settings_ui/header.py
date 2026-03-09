# app/ui/settings_ui/header.py
from nicegui import ui
from typing import Callable


def create_header(on_save: Callable, on_exit: Callable):
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
            ui.button("EXIT", on_click=on_exit).props(
                "flat dense color=grey text-color=grey-4 no-caps"
            )
            ui.button("APPLY CHANGES", on_click=on_save).props(
                "unelevated dense color=cyan-7 text-color=white icon=save no-caps"
            ).classes("px-4 font-bold")
