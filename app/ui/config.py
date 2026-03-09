# app/ui/config.py
# schema 통일 (label / axis 추가)
METRICS: list[dict[str, object]] = [
    {"key": "do", "label": "DO (mg/L)", "unit": "mg/L", "axis": 0},
    {"key": "mlss", "label": "MLSS (mg/L)", "unit": "mg/L", "axis": 1},
    {"key": "temp", "label": "Temp (°C)", "unit": "°C", "axis": 2},
    {"key": "ph", "label": "pH", "unit": "", "axis": 3},
    {"key": "air_flow", "label": "Air Flow (L/min)", "unit": "L/min", "axis": 4},
    {"key": "pump_hz", "label": "Pump Hz (Hz)", "unit": "Hz", "axis": 5},
    {"key": "power", "label": "Power (kW)", "unit": "kW", "axis": 6},
    {"key": "energy", "label": "Energy (kWh)", "unit": "kWh", "axis": 7},
]

# [CHANGED] axis 포지션(left/right + offset) 생성
AXIS_POSITIONS: list[tuple[str, int]] = [
    ("left" if i % 2 == 0 else "right", (i // 2) * 40) for i in range(len(METRICS))
]

FONT_SCALES: dict[str, int] = {"xs": 10, "sm": 12, "md": 14, "lg": 16}
BUCKETS: list[str] = ["5 s", "10 s", "30 s", "1 m", "5 m"]
