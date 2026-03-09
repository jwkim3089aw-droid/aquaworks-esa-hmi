# app/adapters/plc/modbus/map.py
# [PATCHED] AquaEsa_TV1.0.13 PCB 전용 Modbus RTU 레지스터 맵
from __future__ import annotations
from dataclasses import dataclass


# ------------------------------------------------------------------
# 유틸리티 함수
# ------------------------------------------------------------------
def clamp_u16(v: int) -> int:
    """Modbus 16비트 레지스터(ushort) 범위를 초과하지 않도록 제한"""
    return max(0, min(0xFFFF, int(v)))


# ------------------------------------------------------------------
# 1. Coils (0x01 Read, 0x05/0x0F Write) - 비트(bool) 제어
# ------------------------------------------------------------------
COIL_EMERGENCY = 0  # 비상정지 상태 (읽기 전용 상태 체크용)
COIL_PUMP_POWER = 1  # 펌프 전원 (1: ON, 0: OFF)
COIL_PUMP_AUTO = 2  # 펌프 동작 모드 (1: AUTO, 0: MANUAL)
COIL_VALVE_POWER = 3  # 밸브 전원 (1: ON, 0: OFF)
COIL_VALVE_AUTO = 4  # 밸브 동작 모드 (1: AUTO, 0: MANUAL) - C# 중복 할당 버그 패치 (3->4)

COIL_SIZE = 16  # 읽어올 총 코일 개수 (nRxCcnt = 16)


# ------------------------------------------------------------------
# 2. Holding Registers (40001+) 오프셋(0-base) (0x03 Read, 0x06/0x10 Write)
# ------------------------------------------------------------------
# -- 펌프 스케줄 파라미터 (11 ~ 28) --
# [구간 시작값(Low), 구간 종료값(High), 설정 주파수(Freq)]
HR_PUMP_LO_1 = 11
HR_PUMP_HI_1 = 12
HR_PUMP_FR_1 = 13
HR_PUMP_LO_2 = 14
HR_PUMP_HI_2 = 15
HR_PUMP_FR_2 = 16
HR_PUMP_LO_3 = 17
HR_PUMP_HI_3 = 18
HR_PUMP_FR_3 = 19
HR_PUMP_LO_4 = 20
HR_PUMP_HI_4 = 21
HR_PUMP_FR_4 = 22
HR_PUMP_LO_5 = 23
HR_PUMP_HI_5 = 24
HR_PUMP_FR_5 = 25
HR_PUMP_LO_6 = 26
HR_PUMP_HI_6 = 27
HR_PUMP_FR_6 = 28

HR_PUMP_MANUAL_FREQ = 29  # 펌프 수동 조작 시 주파수 설정값 (nPmnf)
HR_VALVE_MANUAL_INT = 30  # 밸브 수동 조작 시 강도 설정값 (nVmni)

# -- 밸브 스케줄 파라미터 (31 ~ 48) --
# [구간 시작값(Low), 구간 종료값(High), 설정 강도(Intensity)]
HR_VALVE_LO_1 = 31
HR_VALVE_HI_1 = 32
HR_VALVE_IT_1 = 33
HR_VALVE_LO_2 = 34
HR_VALVE_HI_2 = 35
HR_VALVE_IT_2 = 36
HR_VALVE_LO_3 = 37
HR_VALVE_HI_3 = 38
HR_VALVE_IT_3 = 39
HR_VALVE_LO_4 = 40
HR_VALVE_HI_4 = 41
HR_VALVE_IT_4 = 42
HR_VALVE_LO_5 = 43
HR_VALVE_HI_5 = 44
HR_VALVE_IT_5 = 45
HR_VALVE_LO_6 = 46
HR_VALVE_HI_6 = 47
HR_VALVE_IT_6 = 48

# -- 시스템 및 알람 레지스터 --
HR_DEVICE_ID = 49  # 장비 ID (nHid)
HR_EXCEPTION = 52  # 알람/에러 상태 (nHexc)
# -> Bit 1 (0x0002): 인버터 통신 에러
# -> Bit 2 (0x0004): 전력계 통신 에러
HR_CONFIG_ID = 60  # Config ID

HR_SIZE = 64  # 읽어올 총 레지스터 개수 (넉넉하게 64 버퍼 할당)

# (Input Register는 C# 프로토콜 상 사용하지 않으므로 제거)
IR_SIZE = 0


# ------------------------------------------------------------------
# HMI 초기 실행 시 들어갈 기본값 세팅 (UI 상태 동기화용)
# ------------------------------------------------------------------
@dataclass
class Defaults:
    # 코일 초기 상태
    pump_power: bool = False
    pump_auto: bool = True
    valve_power: bool = False
    valve_auto: bool = True
    emergency: bool = False

    # 펌프/밸브 수동 기본값
    pump_manual_freq: int = 40
    valve_manual_int: int = 50


DEFAULTS = Defaults()
