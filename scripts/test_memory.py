import time
from pymodbus.client import ModbusTcpClient

# ==========================================
# 🎯 타겟 통신 설정 (테스트할 기기 정보)
# ==========================================
HOST = "127.0.0.1"
PORT = 5020
UNIT_ID = 1  # Slave ID


def verify_modbus_memory():
    print(f"📡 {HOST}:{PORT} (Slave: {UNIT_ID}) 연결 시도 중...")

    # Modbus TCP 클라이언트 객체 생성
    client = ModbusTcpClient(HOST, port=PORT)

    if not client.connect():
        print(f"🔴 연결 실패! 시뮬레이터나 장비가 {HOST}:{PORT}에서 켜져 있는지 확인하세요.")
        return

    print("🟢 연결 성공! 데이터 읽기를 시작합니다.\n")
    print("=" * 45)

    try:
        # --------------------------------------------------
        # 1. Coils (0/1 디지털 상태 읽기)
        # --------------------------------------------------
        print("💡 [Coils] 상태 제어 영역 (주소 0 ~ 3)")
        # 주소 0번부터 4개의 데이터를 읽어옴
        coils_req = client.read_coils(address=0, count=4, slave=UNIT_ID)

        if not coils_req.isError():
            print(f"  [0] 비상정지 상태     : {'ON (비상)' if coils_req.bits[0] else 'OFF (정상)'}")
            print(f"  [1] 펌프 전원         : {'ON' if coils_req.bits[1] else 'OFF'}")
            print(f"  [2] 펌프 자동/수동    : {'Auto' if coils_req.bits[2] else 'Manual'}")
            print(f"  [3] 밸브 전원         : {'ON' if coils_req.bits[3] else 'OFF'}")
        else:
            print("  ⚠️ Coils 읽기 실패 (장비에서 지원하지 않거나 주소 오류)")

        print("-" * 45)

        # --------------------------------------------------
        # 2. Holding Registers (센서 데이터 읽기)
        # --------------------------------------------------
        print("📊 [Holding] 센서 데이터 영역 (주소 0 ~ 10)")
        h_sensors = client.read_holding_registers(address=0, count=11, slave=UNIT_ID)

        if not h_sensors.isError():
            regs = h_sensors.registers
            # 아날로그 값은 장비 내부적으로 100을 곱해서(소수점 제거) 보낼 수 있습니다.
            print(f"  [0] DO (용존산소)     : {regs[0]} (원시값)")
            print(f"  [1] pH (산성도)       : {regs[1]} (원시값)")
            print(f"  [2] Temp (온도)       : {regs[2]} (원시값)")
            print(f"  [7~8] 현재 전력 소비량: [{regs[7]}, {regs[8]}]")
            print(f"  [9~10] 누적 전력량    : [{regs[9]}, {regs[10]}]")
        else:
            print("  ⚠️ 센서 Holding Registers 읽기 실패")

        print("-" * 45)

        # --------------------------------------------------
        # 3. Holding Registers (펌프/밸브 수동 제어값)
        # --------------------------------------------------
        print("🎛️ [Holding] 수동 제어 설정값 (주소 29 ~ 30)")
        h_ctrl = client.read_holding_registers(address=29, count=2, slave=UNIT_ID)

        if not h_ctrl.isError():
            print(f"  [29] 펌프 수동 주파수 : {h_ctrl.registers[0]} Hz")
            print(f"  [30] 밸브 수동 개도율 : {h_ctrl.registers[1]} %")
        else:
            print("  ⚠️ 제어 Holding Registers 읽기 실패")

        print("-" * 45)

        # --------------------------------------------------
        # 4. Holding Registers (시스템 정보)
        # --------------------------------------------------
        print("🖥️ [Holding] 시스템 상태 (주소 49, 52)")
        h_sys = client.read_holding_registers(address=49, count=4, slave=UNIT_ID)

        if not h_sys.isError():
            print(f"  [49] 기기 ID          : {h_sys.registers[0]}")
            print(f"  [52] 예외 코드 (Excpt): {h_sys.registers[3]}")
        else:
            print("  ⚠️ 시스템 Holding Registers 읽기 실패")

    except Exception as e:
        print(f"\n🚨 데이터 읽기 중 치명적 오류 발생: {e}")

    finally:
        client.close()
        print("=" * 45)
        print("🏁 통신 테스트 종료 및 소켓 닫힘")


if __name__ == "__main__":
    verify_modbus_memory()
