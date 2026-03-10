# scripts/test_physics.py
import os
import sys
import time

# 🚀 [핵심] 현재 스크립트 위치와 상관없이 무조건 'code' 폴더 최상위를 파이썬 경로에 강제 추가!
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 이제 무조건 simulator 모듈을 찾을 수 있습니다.
from simulator.model import ESAProcessModel


def print_state(step_name: str, model: ESAProcessModel):
    print(f"[{step_name}]")
    print(f" ⚙️ Control  | Pump: {model.pump_hz:>4.1f} Hz  /  Valve: {model.valve_open:>5.1f} %")
    print(f" 💨 Air Flow | {model.air_flow:>6.1f} LPM")
    print(f" 💧 DO       | {model.do:>6.2f} mg/L")
    print(f" 🧪 pH       | {model.ph:>6.2f}")
    print(f" 🦠 MLSS     | {model.mlss:>6.1f} mg/L")
    print("-" * 50)


def fast_forward(model: ESAProcessModel, hours: float, dt: float = 2.0):
    """지정된 시간(hours)만큼 물리 엔진의 시간을 강제로 빠르게 돌립니다."""
    steps = int((hours * 3600) / dt)
    for _ in range(steps):
        model._substep(dt)
        model._update_sensors(dt)


def run_tests():
    print("=" * 50)
    print("🚀 ESA 물리 엔진(Digital Twin) 단독 가혹 테스트 🚀")
    print("=" * 50 + "\n")

    # 1. 모델 초기화
    model = ESAProcessModel()
    print_state("초기 상태 (0시간)", model)

    # ---------------------------------------------------------
    # 시나리오 1: 펌프는 최대로 돌지만 밸브를 꽉 잠갔을 때 (질식 상태)
    # ---------------------------------------------------------
    print("\n▶ [시나리오 1] 펌프 50Hz 풀가동, 하지만 밸브는 0% (2시간 경과)")
    model.set_controls(pump_hz=50.0, valve_open_pct=0.0)
    fast_forward(model, hours=2.0)
    print_state("결과 (2시간 후)", model)

    # ---------------------------------------------------------
    # 시나리오 2: 밸브를 100% 완전 개방했을 때 (급속 폭기)
    # ---------------------------------------------------------
    print("\n▶ [시나리오 2] 펌프 50Hz 유지, 밸브 100% 완전 개방 (2시간 경과)")
    model.set_controls(pump_hz=50.0, valve_open_pct=100.0)
    fast_forward(model, hours=2.0)
    print_state("결과 (4시간 후)", model)

    # ---------------------------------------------------------
    # 시나리오 3: AI가 적당히 조절했을 때 (유지 상태)
    # ---------------------------------------------------------
    print("\n▶ [시나리오 3] 펌프 40Hz로 감속, 밸브 60%로 조절 (2시간 경과)")
    model.set_controls(pump_hz=40.0, valve_open_pct=60.0)
    fast_forward(model, hours=2.0)
    print_state("결과 (6시간 후)", model)


if __name__ == "__main__":
    run_tests()
