import asyncio
import logging
import json
import sys
import os
import time
import argparse
from pathlib import Path

# --- 통신 라이브러리 ---
from asyncua import Server
from pymodbus.server import StartAsyncTcpServer
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext

# --- 물리 엔진 ---
from simulator.model import ESAProcessModel

# =========================================================
# [설정 1] 인코딩 강제 설정 (Windows CP949 에러 방지)
# =========================================================
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level):
        self.max_level = max_level

    def filter(self, record):
        return record.levelno < self.max_level


def setup_standard_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.addFilter(MaxLevelFilter(logging.ERROR))
    stdout_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"))

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(logging.Formatter("%(asctime)s | 🛑 %(levelname)-7s | %(message)s"))

    logger.addHandler(stdout_handler)
    logger.addHandler(stderr_handler)
    return logger


logger = setup_standard_logger("ESA_HYBRID_SIM")
logging.getLogger("asyncua").setLevel(logging.WARNING)
logging.getLogger("pymodbus").setLevel(logging.WARNING)

# =========================================================
# [설정 2] 🚀 메모리 맵 (3D 대시보드 연동용 밸브 피드백 추가)
# =========================================================
AUTO_SAVE_INTERVAL = 5.0

# 1. Modbus Coils (0/1 제어)
CO_EMG = 0
CO_PUMP_PWR = 1
CO_PUMP_AUTO = 2
CO_VALVE_PWR = 3

# 2. Modbus Holding Registers (센서 및 설정)
HR_DO = 0
HR_PH = 1
HR_TEMP = 2
HR_FLOW = 3
HR_MLSS = 4
HR_VALVE_CURR = 5  # 🚀 [패치] 3D 대시보드가 읽어갈 밸브 현재 상태! (마이크 ON)
HR_PUMP_CURR = 6
HR_POWER_CURR = 7
HR_POWER_ACCM = 9
HR_PUMP_TARGET = 29
HR_VALVE_TARGET = 30
HR_ID = 49
HR_EXCPT = 52

# 🎯 [핵심 패치] 저장소 경로를 `simulator/.data/` 로 영구 고정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, ".data")

# .data 폴더가 없으면 알아서 생성합니다.
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"📁 데이터 저장 폴더 생성 완료: {DATA_DIR}")

SAVE_FILE_PREFIX = "esa_save_data"


# =========================================================
# [메인 로직] 하이브리드 서버 실행
# =========================================================
async def run_server(opc_port: int, modbus_port: int):
    # 🎯 [핵심 패치] 이제 파일은 무조건 `.data` 폴더 안에 쌓입니다.
    save_file = os.path.join(DATA_DIR, f"{SAVE_FILE_PREFIX}_{modbus_port}.json")
    rtu_id = modbus_port - 5020 + 1

    esa_model = ESAProcessModel()

    if os.path.exists(save_file):
        try:
            with open(save_file, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                esa_model.load_snapshot(saved_data)
                logger.info(f"📂 저장된 데이터 불러오기 성공 ({save_file})")
        except Exception as e:
            logger.error(f"데이터 로드 실패: {e}")
    else:
        logger.info(f"ℹ️ 저장된 데이터가 없습니다. 새로 시작합니다. (RTU {rtu_id})")

    store = ModbusSlaveContext(
        di=ModbusSequentialDataBlock(0, [0] * 100),
        co=ModbusSequentialDataBlock(0, [0] * 100),
        ir=ModbusSequentialDataBlock(0, [0] * 100),
        hr=ModbusSequentialDataBlock(0, [0] * 100),
    )
    modbus_context = ModbusServerContext(slaves=store, single=True)

    identity = ModbusDeviceIdentification()
    identity.VendorName = "AquaWorks"
    identity.ModelName = f"Hybrid_Sim_RTU_{rtu_id}"

    # Modbus 초기값 세팅 (Holding Registers)
    store.setValues(3, HR_ID, [rtu_id])
    store.setValues(3, HR_EXCPT, [0])
    store.setValues(3, HR_PUMP_TARGET, [int(esa_model.pump_hz * 10)])
    store.setValues(3, HR_VALVE_TARGET, [int(esa_model.valve_open)])

    # Modbus 초기값 세팅 (Coils)
    store.setValues(1, CO_EMG, [0])
    store.setValues(1, CO_PUMP_PWR, [1])
    store.setValues(1, CO_PUMP_AUTO, [1])
    store.setValues(1, CO_VALVE_PWR, [1])

    modbus_task = asyncio.create_task(
        StartAsyncTcpServer(
            context=modbus_context, identity=identity, address=("0.0.0.0", modbus_port)
        )
    )

    opc_server = Server()
    await opc_server.init()

    opc_endpoint = f"opc.tcp://0.0.0.0:{opc_port}/freeopcua/server/"
    opc_server.set_endpoint(opc_endpoint)

    async with opc_server:
        uri = "http://aquaworks.co.kr/ESA"
        idx = await opc_server.register_namespace(uri)
        folder = await opc_server.nodes.objects.add_folder(f"ns={idx};s=ESA_System", "ESA_System")

        # OPC UA 노드 생성
        p_do = await folder.add_variable(f"ns={idx};s=DO", "DO", 0.0)
        p_ph = await folder.add_variable(f"ns={idx};s=pH", "pH", 0.0)
        p_temp = await folder.add_variable(f"ns={idx};s=Temp", "Temp", 0.0)
        p_flow = await folder.add_variable(f"ns={idx};s=Flow", "Flow", 0.0)
        p_mlss = await folder.add_variable(f"ns={idx};s=MLSS", "MLSS", 0.0)
        p_power = await folder.add_variable(f"ns={idx};s=Power", "Power", 0.0)
        p_energy = await folder.add_variable(f"ns={idx};s=Energy", "Energy", 0.0)

        p_hz = await folder.add_variable(f"ns={idx};s=PumpHz", "PumpHz", float(esa_model.pump_hz))
        p_valve = await folder.add_variable(
            f"ns={idx};s=ValvePos", "ValvePos", float(esa_model.valve_open)
        )
        p_reset = await folder.add_variable(f"ns={idx};s=ResetCmd", "ResetCmd", False)

        await p_hz.set_writable()
        await p_valve.set_writable()
        await p_reset.set_writable()

        logger.info("=" * 60)
        logger.info(f"✅ 하이브리드 시뮬레이터 [RTU {rtu_id}] 가동 완료!")
        logger.info(f"  📡 OPC UA : {opc_endpoint}")
        logger.info(f"  📡 Modbus : 0.0.0.0:{modbus_port}")
        logger.info(f"  💾 저장소   : {DATA_DIR}")
        logger.info("=" * 60)

        last_save_time = time.time()
        last_log_time = time.time()

        while True:
            try:
                if await p_reset.read_value():
                    logger.warning(f"♻️ [RTU {rtu_id}] 리셋 명령 수신...")
                    esa_model.reset()
                    await p_hz.write_value(0.0)
                    await p_valve.write_value(0.0)
                    await p_energy.write_value(0.0)
                    store.setValues(3, HR_PUMP_TARGET, [0])
                    store.setValues(3, HR_VALVE_TARGET, [0])

                    if os.path.exists(save_file):
                        try:
                            os.remove(save_file)
                        except Exception:
                            pass

                    await p_reset.write_value(False)
                    await asyncio.sleep(0.1)
                    continue

                mb_hz_raw = store.getValues(3, HR_PUMP_TARGET, 1)[0]
                mb_valve_raw = store.getValues(3, HR_VALVE_TARGET, 1)[0]
                mb_hz = mb_hz_raw / 10.0
                mb_valve = float(mb_valve_raw)

                opc_hz = await p_hz.read_value()
                opc_valve = await p_valve.read_value()

                if abs(mb_hz - esa_model.pump_hz) > 0.1:
                    esa_model.pump_hz = mb_hz
                    await p_hz.write_value(float(mb_hz))
                elif abs(float(opc_hz) - esa_model.pump_hz) > 0.1:
                    esa_model.pump_hz = float(opc_hz)
                    store.setValues(3, HR_PUMP_TARGET, [int(opc_hz * 10)])

                if abs(mb_valve - esa_model.valve_open) > 0.1:
                    logger.info(
                        f"🚰 [RTU {rtu_id}] 밸브 명령 수신! (현재: {esa_model.valve_open}% -> 변경: {mb_valve}%)"
                    )
                    esa_model.valve_open = mb_valve
                    await p_valve.write_value(float(mb_valve))
                elif abs(float(opc_valve) - esa_model.valve_open) > 0.1:
                    esa_model.valve_open = float(opc_valve)
                    store.setValues(3, HR_VALVE_TARGET, [int(opc_valve)])

            except Exception as e:
                logger.error(f"[RTU {rtu_id}] Read Error: {e}")

            esa_model.update()

            if time.time() - last_log_time > 2.0:
                if esa_model.pump_hz > 10.0 and esa_model.power < 0.1:
                    logger.warning(
                        f"⚠️ [RTU {rtu_id}] Hz:{esa_model.pump_hz:.1f} | Power:{esa_model.power:.3f} kW (물 안 흐름!)"
                    )
                last_log_time = time.time()

            try:
                await p_do.write_value(float(esa_model.do))
                await p_ph.write_value(float(esa_model.ph))
                await p_temp.write_value(float(esa_model.temp))
                await p_flow.write_value(float(esa_model.air_flow))
                await p_mlss.write_value(float(esa_model.mlss))
                await p_power.write_value(float(esa_model.power))
                await p_energy.write_value(float(esa_model.energy))

                store.setValues(3, HR_DO, [int(esa_model.do * 100)])
                store.setValues(3, HR_PH, [int(esa_model.ph * 100)])
                store.setValues(3, HR_TEMP, [int(esa_model.temp * 100)])
                store.setValues(3, HR_FLOW, [int(esa_model.air_flow * 10)])
                store.setValues(3, HR_MLSS, [int(esa_model.mlss)])

                # 🚀 [패치 완료] 3D 대시보드로 밸브 상태를 소리쳐서 알려줌! (5번 주소)
                store.setValues(3, HR_VALVE_CURR, [int(esa_model.valve_open)])

                store.setValues(3, HR_PUMP_CURR, [int(esa_model.pump_hz * 10)])
                store.setValues(3, HR_POWER_CURR, [int(esa_model.power * 100)])
                store.setValues(3, HR_POWER_ACCM, [int(esa_model.energy * 10)])

            except Exception as e:
                logger.error(f"[RTU {rtu_id}] Write Error: {e}")

            now = time.time()
            if now - last_save_time > AUTO_SAVE_INTERVAL:
                try:
                    data_to_save = esa_model.get_snapshot()
                    with open(save_file, "w", encoding="utf-8") as f:
                        json.dump(data_to_save, f, indent=4)
                    last_save_time = now
                except Exception as e:
                    logger.error(f"[RTU {rtu_id}] 저장 실패: {e}")

            await asyncio.sleep(0.1)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    parser = argparse.ArgumentParser()
    parser.add_argument("--opc-port", type=int, default=4845, help="OPC UA Server Port")
    parser.add_argument("--modbus-port", type=int, default=5020, help="Modbus TCP Server Port")
    args = parser.parse_args()

    try:
        asyncio.run(run_server(args.opc_port, args.modbus_port))
    except KeyboardInterrupt:
        logger.info(f"서버 (OPC:{args.opc_port}, MB:{args.modbus_port}) 종료")
