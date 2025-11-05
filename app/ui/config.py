# app/ui/config.py
from __future__ import annotations

from typing import Any

API_BASE = "http://127.0.0.1:8003"

# 워터톤 팔레트 (라이트 기본, 다크 대응 색도 지정)
THEME: dict[str, str] = {
    "primary": "#10a5a5",  # teal-500 계열
    "accent": "#2563eb",  # blue-600
    "bg": "#f6f9fc",  # 거의 화이트
    "card": "#ffffff",
    "border": "#e6edf5",
    "ink": "#0f172a",  # slate-900
    "ink_sub": "#64748b",  # slate-500
}

METRICS: list[dict[str, Any]] = [
    {"key": "DO", "label": "DO (mg/L)", "axis": 0, "unit": "mg/L"},
    {"key": "air_flow", "label": "Air Flow (L/min)", "axis": 1, "unit": "L/min"},
    {"key": "MLSS", "label": "MLSS (mg/L)", "axis": 2, "unit": "mg/L"},
    {"key": "power", "label": "Power (kW)", "axis": 3, "unit": "kW"},
    {"key": "temp", "label": "Temp (°C)", "axis": 4, "unit": "°C"},
    {"key": "pH", "label": "pH", "axis": 5, "unit": ""},
]

AXIS_POSITIONS: list[tuple[str, int]] = [
    ("left", 0),
    ("right", 0),
    ("left", 55),
    ("right", 55),
    ("left", 110),
    ("right", 110),
]

FONT_SCALES = {"S": 13, "M": 15, "L": 17}
