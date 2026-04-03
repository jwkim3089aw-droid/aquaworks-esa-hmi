# app/ui/common.py
import os
import math
import logging
from typing import Dict, Tuple, Any, Optional

# 🚀 [ADD] 중앙 통제식 설정 임포트
from app.core.config import get_settings


# ---------------------------------------------------------------------------
# 로깅 설정
# ---------------------------------------------------------------------------
def setup_logging() -> logging.Logger:
    settings = get_settings()

    # 1. 파일명 정규화 (UI/Web 전용 로그임을 명확히)
    log_file_path = settings.APP_LOG_DIR / "web_ui.log"

    fh = logging.FileHandler(log_file_path, encoding="utf-8")
    fh.setLevel(logging.INFO)

    # 2. 정석 포맷: [시간] [로그레벨] [모듈명] 메시지
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    fh.setFormatter(fmt)

    # 3. Root Logger가 아닌, 'esa_hmi.ui' 전용 로거에만 핸들러 장착 (완벽한 격리)
    logger = logging.getLogger("esa_hmi.ui")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        logger.addHandler(fh)

    # (선택) UI 로그가 Root로 올라가서 다른 파일에 중복 기록되는 것을 차단
    logger.propagate = False

    return logger


log = setup_logging()

# ---------------------------------------------------------------------------
# 전역 스타일 (CSS)
# ---------------------------------------------------------------------------
APP_CSS = """
<style>
  .pm-txt {
    display:inline-block; padding:0 4px; color:#fff !important;
    background:transparent!important; border:none!important; box-shadow:none!important;
    line-height:1; font-size:18px; user-select:none; cursor:pointer; vertical-align:middle;
  }
  .pm-txt:hover { color:#e5e7eb !important; }
  .pm-txt:active { transform:translateY(0.5px); }
  .cmds input[type=number]::-webkit-inner-spin-button,
  .cmds input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  .cmds input[type=number] { -moz-appearance: textfield; }
  .cmds .q-field__control { padding-left: 4px !important; padding-right: 4px !important; min-height: 30px; }
  .cmds .q-field__native { padding: 0 4px !important; }
  .cmds .q-field__prepend, .cmds .q-field__append { padding: 0 2px !important; }
  .cmds .pm-txt { padding: 0 2px; font-size: 16px; }
  .cmds .cmd-header-cell { display: flex; align-items: center; justify-content: center; height: 32px; }
  .metric-card-wrapper { cursor: grab; }
  .metric-card-wrapper:active { cursor: grabbing; }
  .metric-card-wrapper--active { transform: translateX(6px); }
  .duration-select .q-field__control { min-height: 24px !important; height: 24px !important; padding-top: 0 !important; padding-bottom: 0 !important; }
  .duration-select .q-field__inner { padding-top: 0 !important; padding-bottom: 0 !important; }
  .duration-select .q-field__control-container { align-items: center !important; padding-top: 0 !important; padding-bottom: 0 !important; }
  .duration-select .q-field__native { padding-top: 0 !important; padding-bottom: 0 !important; display: flex !important; align-items: center !important; }
  .duration-select .q-field__marginal { height: 24px !important; display: flex !important; align-items: center !important; }
  .duration-select .q-field__input { line-height: 1 !important; }
  .hide-scrollbar::-webkit-scrollbar { display: none; }
  .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
  .custom-scrollbar::-webkit-scrollbar { height: 10px; }
  .custom-scrollbar::-webkit-scrollbar-track { background: #111827; border-radius: 0 0 8px 8px; }
  .custom-scrollbar::-webkit-scrollbar-thumb { background: #374151; border-radius: 5px; border: 2px solid #111827; }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #4B5563; }
</style>
"""


# ---------------------------------------------------------------------------
# 유틸리티 함수
# ---------------------------------------------------------------------------
def title_of(m: Dict[str, Any]) -> str:
    return str(m.get("title") or m.get("label") or m.get("key") or "")


def metric_name_and_unit(m: Dict[str, Any]) -> Tuple[str, str]:
    key = str(m.get("key") or "").lower()
    unit_raw = str(m.get("unit") or "").strip()

    default_unit = ""
    if key in ("do", "mlss"):
        default_unit = "mg/L"
    elif key in ("air_flow", "airflow"):
        default_unit = "L/min"
    elif key == "power":
        default_unit = "kW"
    elif key == "energy":
        default_unit = "kWh"

    lu = unit_raw.lower()
    unit = unit_raw
    if "mg/l" in lu:
        unit = "mg/L"
    elif "l/min" in lu:
        unit = "L/min"
    elif "kw" in lu and "kwh" not in lu:
        unit = "kW"
    elif "kwh" in lu:
        unit = "kWh"

    if not unit:
        unit = default_unit

    base = ""
    if key == "do":
        base = "DO"
    elif key == "mlss":
        base = "MLSS"
    elif key == "temp":
        base = "Temp"
    elif key == "ph":
        base = "pH"
    elif key in {"air_flow", "airflow"}:
        base = "Air Flow"
    elif key == "power":
        base = "Power"
    elif key == "energy":
        base = "Energy"
    else:
        title = title_of(m)
        base = title.split("(")[0].split("[")[0].strip()

    return base, unit


def axis_label_of(m: Dict[str, Any]) -> str:
    base, unit = metric_name_and_unit(m)
    if not unit:
        return base
    return f"{base}\n[{unit}]"


def format_mark_value(key: str, val: Optional[float]) -> str:
    if val is None:
        return "--"
    if isinstance(val, float) and math.isnan(val):
        return "--"
    if key in ("mlss", "air_flow", "pump_hz", "valve_pos"):
        return f"{val:.1f}"
    return f"{val:.2f}"
