# app/ui/charts_ui/utils.py
from typing import Any


def short_ts(s: Any) -> str:
    """긴 시계열 문자열에서 시간 부분만 추출 (HH:MM:SS)"""
    s = str(s or "")
    # "2023-10-25 14:30:00" -> "14:30:00"
    return s.split(" ")[-1] if " " in s else s[-8:]
