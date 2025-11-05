# app/ui/commands.py
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
from nicegui import ui


def build_command_panel(
    api_base: str, add_cmd_history: Callable[[str, str, bool, str], None]
) -> tuple[Any, Any]:
    ui.label("Commands").classes("aw-section-title")

    with ui.card().classes("aw-card p-4 w-full"):
        # Air Setpoint
        with ui.row().classes("items-center gap-3 w-full"):
            ui.label("Air Setpoint (L/min)").classes("aw-subtle text-xs")
            air_set_slider = (
                ui.slider(min=160, max=210, step=0.5, value=190).props("label").classes("w-[280px]")
            )

            async def apply_air(v: float) -> None:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        await client.post(
                            f"{api_base}/api/v1/commands/air_setpoint", json={"value": v}
                        )
                    ui.notify(f"Air setpoint: {v:.1f} L/min", color="positive")
                    add_cmd_history("air_setpoint", f"{v:.1f}", True, "-")
                except Exception as e:
                    ui.notify(f"Air setpoint failed: {e}", color="negative")
                    add_cmd_history("air_setpoint", f"{v:.1f}", False, str(e))

            ui.button(
                "적용", on_click=lambda: asyncio.create_task(apply_air(float(air_set_slider.value)))
            ).classes("aw-btn")

        # Pump Hz
        with ui.row().classes("items-center gap-3 w-full mt-2"):
            ui.label("Pump Hz Setpoint (Hz)").classes("aw-subtle text-xs")
            pump_hz_slider = (
                ui.slider(min=20, max=60, step=0.5, value=45).props("label").classes("w-[260px]")
            )

            async def apply_pump(v: float) -> None:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        await client.post(
                            f"{api_base}/api/v1/commands/pump_hz_setpoint",
                            json={"value": v},
                        )
                    ui.notify(f"Pump Hz: {v:.1f} Hz", color="positive")
                    add_cmd_history("pump_hz_setpoint", f"{v:.1f}", True, "-")
                except Exception as e:
                    ui.notify(f"Pump Hz failed: {e}", color="negative")
                    add_cmd_history("pump_hz_setpoint", f"{v:.1f}", False, str(e))

            ui.button(
                "적용",
                on_click=lambda: asyncio.create_task(apply_pump(float(pump_hz_slider.value))),
            ).classes("aw-btn")

    return air_set_slider, pump_hz_slider
