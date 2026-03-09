# app/api/v1/status.py
from fastapi import APIRouter
from app.stream.state import sys_state

# -----------------------------------------------------------------------------
# Router Setup
# -----------------------------------------------------------------------------
router = APIRouter(prefix="/api/v1/status", tags=["status"])


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@router.get("/")
async def check_api_health():
    """기본 API 서버 상태 확인용"""
    return {"status": "ok", "service": "ESA_HMI_API"}


@router.get("/realtime")
async def get_realtime_status():
    """
    프론트엔드(React/Next.js)에서 주기적으로 호출하여
    HMI 대시보드 화면에 펌프와 밸브의 현재 상태를 렌더링합니다.
    """
    return {
        "pump": {
            # Poller가 읽어온 Coils 상태
            "power": getattr(sys_state, "pump_power", False),
            "auto_mode": getattr(sys_state, "pump_auto", True),
        },
        "valve": {
            "power": getattr(sys_state, "valve_power", False),
            "auto_mode": getattr(sys_state, "valve_auto", True),
        },
        "system": {
            # 비상 정지 코일 상태 (True면 알람 화면 띄우기)
            "emergency_stop": getattr(sys_state, "emergency", False),
        },
    }
