from __future__ import annotations

import io
import os
import subprocess
import sys
import time

# 한글 출력을 위한 인코딩 강제 설정
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore

# =========================================================
# 🚀 다중 시뮬레이터 띄우기 설정 (현재 3대로 세팅, 10대로 하려면 range(10)으로 변경)
# =========================================================
SIMULATORS = []
for i in range(3):
    SIMULATORS.append(
        {
            "opc_port": 4845 + i,  # 4845, 4846, 4847...
            "modbus_port": 5020 + i,  # 5020, 5021, 5022...
        }
    )


def main() -> None:
    simulator_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(simulator_dir)
    env = os.environ.copy()
    env["PYTHONPATH"] = project_root + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    processes = []

    print("🚀 [1/2] 물리 엔진 기반 시뮬레이터(simulator.main) 다중 실행 시작...")

    for i, sim in enumerate(SIMULATORS, 1):
        cmd = [
            sys.executable,
            "-u",
            "-m",
            "simulator.main",
            "--opc-port",
            str(sim["opc_port"]),
            "--modbus-port",
            str(sim["modbus_port"]),
        ]
        print(f"   ▶ {i}호기 부팅 중 (OPC: {sim['opc_port']} / Modbus: {sim['modbus_port']})")
        p = subprocess.Popen(cmd, cwd=project_root, env=env)
        processes.append(p)

    # 서버들이 전부 구동될 때까지 안전하게 대기
    time.sleep(3.0)

    print("🚀 [2/2] UI 대시보드 화면 시작 (simulator.ui_app)...")
    ui_process = subprocess.Popen(
        [sys.executable, "-u", "-m", "simulator.ui_app"], cwd=project_root, env=env
    )
    processes.append(ui_process)

    print("=" * 60)
    print(f"✅ 총 {len(SIMULATORS)}대의 장비가 정상 가동 중입니다!")
    print("🛑 종료하려면 Ctrl+C를 누르세요.")
    print("=" * 60)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 일괄 종료 프로세스 시작...")
    finally:
        for p in processes:
            p.terminate()
        time.sleep(1.0)
        for p in processes:
            if p.poll() is None:
                p.kill()
        print("👋 모든 시뮬레이터 프로세스 완전 종료 완료.")


if __name__ == "__main__":
    main()
