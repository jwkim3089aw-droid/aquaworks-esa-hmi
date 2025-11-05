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
    ui.label("Commands & History").classes("text-white/80 text-sm")

    # Air Setpoint
    with ui.row().classes("items-center gap-3"):
        ui.label("Air Setpoint (L/min)").classes("text-white/70")
        air_set_slider = (
            ui.slider(min=160, max=210, step=0.5, value=190)
            .props("label color=teal")
            .classes("w-[280px]")
        )
        spinner_air = ui.spinner("dots").classes("ml-1").props("size=sm").style("visibility:hidden")

        async def apply_air_setpoint(v: float) -> None:
            spinner_air.style("visibility:visible")
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(f"{api_base}/api/v1/commands/air_setpoint", json={"value": v})
                ui.notify(f"Air setpoint applied: {v:.1f} L/min", color="positive")
                add_cmd_history("air_setpoint", f"{v:.1f}", True, "-")
            except Exception as e:
                ui.notify(f"Air setpoint failed: {e}", color="negative")
                add_cmd_history("air_setpoint", f"{v:.1f}", False, str(e))
            finally:
                spinner_air.style("visibility:hidden")

        ui.button(
            "적용",
            on_click=lambda: asyncio.create_task(apply_air_setpoint(float(air_set_slider.value))),
        ).classes("ml-1")

    # Pump Hz
    with ui.row().classes("items-center gap-3"):
        ui.label("Pump Hz Setpoint (Hz)").classes("text-white/70")
        pump_hz_slider = (
            ui.slider(min=20, max=60, step=0.5, value=45)
            .props("label color=teal")
            .classes("w-[260px]")
        )
        spinner_pump = (
            ui.spinner("dots").classes("ml-1").props("size=sm").style("visibility:hidden")
        )

        async def apply_pump_hz(v: float) -> None:
            spinner_pump.style("visibility:visible")
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"{api_base}/api/v1/commands/pump_hz_setpoint", json={"value": v}
                    )
                ui.notify(f"Pump Hz applied: {v:.1f} Hz", color="positive")
                add_cmd_history("pump_hz_setpoint", f"{v:.1f}", True, "-")
            except Exception as e:
                ui.notify(f"Pump Hz failed: {e}", color="negative")
                add_cmd_history("pump_hz_setpoint", f"{v:.1f}", False, str(e))
            finally:
                spinner_pump.style("visibility:hidden")

        ui.button(
            "적용", on_click=lambda: asyncio.create_task(apply_pump_hz(float(pump_hz_slider.value)))
        ).classes("ml-1")

    return air_set_slider, pump_hz_slider
