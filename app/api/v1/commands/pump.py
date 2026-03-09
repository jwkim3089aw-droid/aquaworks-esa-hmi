# app/api/v1/commands/pump.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 앞서 구현한 Poller의 다이렉트 쓰기 함수와 메모리 맵 임포트
from app.workers.modbus_rtu_poller import write_hr_single
from app.adapters.plc.modbus.map import (
    HR_PUMP_MANUAL_FREQ,
    HR_PUMP_FR_1,
    HR_PUMP_FR_2,
    HR_PUMP_FR_3,
    HR_PUMP_FR_4,
    HR_PUMP_FR_5,
    HR_PUMP_FR_6,
)

router = APIRouter(prefix="/api/v1/pump", tags=["pump"])


# ---------------------------------------------------------
# Models
# ---------------------------------------------------------
class SetFreqIn(BaseModel):
    target: str  # "manual", "schedule_1", "schedule_2" 등
    hz: int  # 설정할 주파수 값 (예: 40)


class CommandOut(BaseModel):
    ok: bool
    message: str


# ---------------------------------------------------------
# Endpoints
# ---------------------------------------------------------
@router.post("/set-freq", response_model=CommandOut)
async def set_pump_frequency(payload: SetFreqIn):
    """
    UI에서 펌프 주파수 설정값을 변경할 때 호출됩니다.
    """
    # UI에서 넘겨준 target 문자열을 실제 PCB 레지스터 주소로 매핑
    address_map = {
        "manual": HR_PUMP_MANUAL_FREQ,
        "schedule_1": HR_PUMP_FR_1,
        "schedule_2": HR_PUMP_FR_2,
        "schedule_3": HR_PUMP_FR_3,
        "schedule_4": HR_PUMP_FR_4,
        "schedule_5": HR_PUMP_FR_5,
        "schedule_6": HR_PUMP_FR_6,
    }

    target_addr = address_map.get(payload.target)
    if target_addr is None:
        raise HTTPException(status_code=400, detail="알 수 없는 Target 입니다.")

    # Poller의 큐에 쓰기 명령을 넣고 결과를 기다림 (최대 2초 대기)
    # 실제 장비는 소수점 1자리를 위해 x10을 하는 경우도 있으므로 (예: 40.0Hz -> 400)
    # C# 원본 로직을 참고하여 필요시 payload.hz * 10 으로 수정하세요.
    write_value = payload.hz

    success = await write_hr_single(target_addr, write_value)

    if success:
        return CommandOut(
            ok=True, message=f"{payload.target} 주파수가 {payload.hz}Hz로 설정되었습니다."
        )
    else:
        # 통신이 끊겼거나 큐가 꽉 차서 실패한 경우
        raise HTTPException(status_code=503, detail="PCB 통신 쓰기 실패 (연결 상태를 확인하세요)")
