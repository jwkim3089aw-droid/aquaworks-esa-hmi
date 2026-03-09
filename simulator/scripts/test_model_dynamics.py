import sys
import time
from pathlib import Path

# 🚀 경로 보정: scripts 폴더에서 실행해도 프로젝트 루트를 인식하도록 설정
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent.parent  # C:\Users\a\Desktop\프로젝트\ESA_HMI\code
sys.path.insert(0, str(root_dir))

from simulator.model import ESAProcessModel


def run_diagnostics():
    print("=========================================================")
    print("🚀 ESA 프로세스 물리/화학 모델 동역학 진단 테스트 시작")
    print("=========================================================\n")

    # 모델 인스턴스 생성
    model = ESAProcessModel()

    # 만약 초기 상태가 0이라면 강제로 정상 범위로 초기화 (UI 구동 전 초기화 모사)
    if model.state.ph < 1.0:
        model.state.ph = 7.2
    if model.state.mlss_true_mgL < 100.0:
        model.state.mlss_true_mgL = 3000.0
    if model.state.temp_c < 1.0:
        model.state.temp_c = 20.0

    # 시뮬레이션 환경 변수 설정
    sim_time_hours = 0.0
    dt_sim = 10.0  # 한 번 루프 돌 때마다 10초씩 시뮬레이션 시간 경과
    dt_real = 0.1  # 센서 노이즈 필터링용 가상 현실 시간

    print(
        f"{'Time(h)':>8} | {'Pump(Hz)':>8} | {'Valve(%)':>8} | {'DO(mg/L)':>8} | {'pH':>8} | {'MLSS':>8} | {'Temp(C)':>8} | {'AirFlow':>8}"
    )
    print("-" * 90)

    def run_phase(hours: float, pump_hz: float, valve_pct: float, phase_name: str):
        nonlocal sim_time_hours
        print(
            f"▶ [시나리오] {phase_name} (Pump: {pump_hz}Hz, Valve: {valve_pct}%) - {hours}시간 경과 모사"
        )

        model.set_controls(pump_hz, valve_pct)
        steps = int((hours * 3600) / dt_sim)

        for i in range(steps):
            # 시간에 따른 수학적 적분 강제 실행 (UI 루프 없이 즉시 계산)
            model._substep(dt_sim)
            model._update_sensors(dt_real)

            sim_time_hours += dt_sim / 3600.0

            # 시뮬레이션 시간 기준 1시간마다 결과 출력
            if (i + 1) % int(3600 / dt_sim) == 0:
                print(
                    f"{sim_time_hours:>8.1f} | {model.pump_hz:>8.1f} | {model.valve_open:>8.1f} | "
                    f"{model.do:>8.2f} | {model.ph:>8.2f} | {model.mlss:>8.0f} | "
                    f"{model.temp:>8.1f} | {model.air_flow:>8.1f}"
                )
        print("-" * 90)

    # 1. 일상적인 안정 상태 테스트 (DO가 적정하게 유지될 때 pH와 MLSS 안정성)
    run_phase(hours=6, pump_hz=30.0, valve_pct=50.0, phase_name="표준 안정화 상태")

    # 2. 극한의 산소 공급 상태 (DO 급증 -> 질산화 발생 -> pH 감소 현상 관찰)
    run_phase(
        hours=6, pump_hz=60.0, valve_pct=100.0, phase_name="최대 폭기 (질산화/pH 하락 테스트)"
    )

    # 3. 산소 부족 상태 (DO 고갈 -> 알칼리도 회복 -> pH 상승 현상 관찰)
    run_phase(hours=6, pump_hz=15.0, valve_pct=10.0, phase_name="최소 폭기 (pH 회복 테스트)")

    print("\n✅ 모델 동역학 진단 테스트가 완료되었습니다.")
    print("모든 수치가 허용 범위 내에 있는지 확인해 주세요.")
    print("정상 범위: DO(0~10), pH(6.5~8.0), MLSS(2000~4000)")


if __name__ == "__main__":
    run_diagnostics()
