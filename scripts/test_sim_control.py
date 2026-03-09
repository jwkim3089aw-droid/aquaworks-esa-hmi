# scripts/test_sim_control.py
import time
from pymodbus.client import ModbusTcpClient

# 시뮬레이터 기본 포트 (5020)
IP = "127.0.0.1"
PORT = 5020
SLAVE_ID = 1


def run_test():
    print(f"🔌 시뮬레이터({IP}:{PORT})에 직접 연결을 시도합니다...")
    client = ModbusTcpClient(IP, port=PORT)

    if not client.connect():
        print("❌ 연결 실패! 시뮬레이터가 켜져 있는지 확인하세요.")
        return

    print("✅ 연결 성공!\n")

    # 1. 센서 데이터 읽기 (0번 ~ 9번 주소)
    print("📊 [STEP 1] 현재 센서 데이터 읽기 (0~9번)")
    res = client.read_holding_registers(0, 10, slave=SLAVE_ID)
    if res.isError():
        print("  ❌ 읽기 에러 발생")
    else:
        regs = res.registers
        print(f"  - DO (0번)   : {regs[0] / 100.0} mg/L")
        print(f"  - pH (1번)   : {regs[1] / 100.0}")
        print(f"  - Temp (2번) : {regs[2] / 100.0} °C")
        print(f"  - Flow (3번) : {regs[3] / 10.0} L/min")
        print(f"  - MLSS (4번) : {regs[4]} mg/L")
        print(f"  - 현재 펌프 Hz (6번 예상) : {regs[6] / 10.0} Hz")

    print("\n🚀 [STEP 2] 제어 명령 쏘기 (Pump=45.0Hz, Valve=70%)")
    # C# 규격: 펌프는 *10 배율이므로 45.0Hz -> 450 전송
    # 주소: 펌프 29번, 밸브 30번
    client.write_register(29, 450, slave=SLAVE_ID)
    client.write_register(30, 70, slave=SLAVE_ID)
    print("  - 29번 주소에 450 (45.0Hz) 쓰기 완료")
    print("  - 30번 주소에 70 (70%) 쓰기 완료\n")

    print("⏳ 물리 엔진이 반응할 시간을 줍니다... (3초 대기)")
    time.sleep(3)

    print("\n🔍 [STEP 3] 명령이 잘 먹혔는지 확인하기")
    res_cmd = client.read_holding_registers(29, 2, slave=SLAVE_ID)
    if not res_cmd.isError():
        print(f"  - 설정된 펌프 목표값 (29번) : {res_cmd.registers[0] / 10.0} Hz")
        print(f"  - 설정된 밸브 목표값 (30번) : {res_cmd.registers[1]} %")

    client.close()
    print("\n테스트 종료!")


if __name__ == "__main__":
    run_test()
