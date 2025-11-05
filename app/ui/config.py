# app/ui/config.py
from __future__ import annotations

from typing import Any

API_BASE = "http://127.0.0.1:8003"

METRICS: list[dict[str, Any]] = [
    {"key": "DO", "label": "DO (mg/L)", "axis": 0, "unit": "mg/L"},
    {"key": "air_flow", "label": "Air Flow (L/min)", "axis": 1, "unit": "L/min"},
    {"key": "MLSS", "label": "MLSS (mg/L)", "axis": 2, "unit": "mg/L"},
    {"key": "power", "label": "Power (kW)", "axis": 3, "unit": "kW"},
    {"key": "temp", "label": "Temp (°C)", "axis": 4, "unit": "°C"},
    {"key": "pH", "label": "pH", "axis": 5, "unit": ""},
]

AXIS_POSITIONS: list[tuple[str, int]] = [
    ("left", 0),  # DO
    ("right", 0),  # Air
    ("left", 55),  # MLSS
    ("right", 55),  # Power
    ("left", 110),  # Temp
    ("right", 110),  # pH
]

FONT_SCALES = {"S": 13, "M": 15, "L": 17}
