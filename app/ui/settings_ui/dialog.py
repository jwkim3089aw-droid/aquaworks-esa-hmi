# app/ui/settings_ui/dialog.py
from typing import Dict, Any, Callable
from nicegui import ui


class SourceDialog(ui.dialog):
    def __init__(self, state: Dict[str, Any], on_close_callback: Callable[[str], None]):
        super().__init__()
        self.state = state
        self.on_close_callback = on_close_callback
        self.target_key = ""

        # UI Components
        self.host: ui.input
        self.port: ui.number
        self.uid: ui.number
        self.enable_sw: ui.switch
        self.form_container: ui.column
        self.lbl_info: ui.label

        with (
            self,
            ui.card().classes("w-[400px] bg-[#1e293b] border border-slate-600 p-0 shadow-2xl"),
        ):

            # Header
            with ui.row().classes(
                "w-full bg-slate-800 p-4 items-center justify-between border-b border-slate-700"
            ):
                with ui.column().classes("gap-0"):
                    ui.label("CONNECTION OVERRIDE").classes(
                        "text-sm font-bold text-white tracking-wider"
                    )
                    self.lbl_info = ui.label("Target Tag Info").classes(
                        "text-[10px] text-cyan-400 font-mono"
                    )

                self.enable_sw = ui.switch().props("dense color=cyan keep-color")
                self.enable_sw.on("update:model-value", self._on_toggle)

            # Body
            with ui.column().classes("w-full p-6 gap-4"):
                self.form_container = ui.column().classes("w-full gap-4 transition-all")

                with self.form_container:
                    ui.label("Custom Modbus TCP Source").classes("text-xs text-slate-500 font-bold")

                    self.host = (
                        ui.input("Target IP Address")
                        .props("outlined dense input-class='font-mono'")
                        .classes("w-full")
                    )

                    with ui.row().classes("w-full gap-4"):
                        self.port = (
                            ui.number("Port", format="%.0f")
                            .props("outlined dense input-class='font-mono'")
                            .classes("w-1/2")
                        )
                        self.uid = (
                            ui.number("Unit ID", format="%.0f")
                            .props("outlined dense input-class='font-mono'")
                            .classes("w-1/2")
                        )

                # Disabled Overlay Message
                with ui.column().classes(
                    "w-full items-center justify-center py-4 text-slate-500 italic gap-2"
                ) as overlay:
                    ui.icon("link_off", size="md")
                    ui.label("Using Global System Configuration")
                overlay.bind_visibility_from(self.enable_sw, "value", backward=lambda x: not x)

            # Footer
            with ui.row().classes(
                "w-full bg-slate-900/50 p-3 justify-end gap-2 border-t border-slate-700"
            ):
                ui.button("CANCEL", on_click=self.close).props("flat dense color=grey no-caps")
                ui.button("SAVE CHANGES", on_click=self.save).props(
                    "unelevated dense color=cyan-7 text-color=white icon=save no-caps"
                )

    def _on_toggle(self, e):
        self.form_container.set_visibility(e.value)

    def open_for(self, key: str, label: str):
        self.target_key = key
        self.lbl_info.text = f"TAG: {label} ({key})"

        cfg = self.state["custom_sources"].get(key, {})
        active = cfg.get("enabled", False)

        self.enable_sw.value = active
        self.host.value = cfg.get("host", "192.168.0.200")
        self.port.value = cfg.get("port", 502)
        self.uid.value = cfg.get("unit_id", 1)

        self.form_container.set_visibility(active)
        self.open()

    def save(self):
        k = self.target_key
        if self.enable_sw.value:
            self.state["custom_sources"][k] = {
                "enabled": True,
                "host": self.host.value,
                "port": int(self.port.value or 0),
                "unit_id": int(self.uid.value or 1),
            }
        else:
            if k in self.state["custom_sources"]:
                del self.state["custom_sources"][k]

        self.on_close_callback(k)
        self.close()
