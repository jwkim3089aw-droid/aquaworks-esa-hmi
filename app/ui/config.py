# app/ui/config.py
from __future__ import annotations

from typing import Any

API_BASE = "http://127.0.0.1:8003"

# [CHANGED] 다크 테마 팔레트
THEME: dict[str, str] = {
    "primary": "#14b8a6",  # teal-500
    "accent": "#60a5fa",  # blue-400
    "bg": "#0b1220",  # 거의 블랙에 가까운 남색
    "card": "#0f172a",  # 슬레이트-900 카드
    "panel": "#0b1324",  # 패널 배경
    "border": "#1f2937",  # 보더
    "ink": "#e5e7eb",  # 기본 텍스트(밝음)
    "ink_sub": "#94a3b8",  # 보조 텍스트
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
