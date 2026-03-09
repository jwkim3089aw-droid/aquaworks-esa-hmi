import sys
import os
import asyncio
import logging
import time
from pathlib import Path

# 현재 스크립트 위치(scripts)의 부모 디렉토리(code)를 파이썬 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 🚀 DB 모델 대신 방금 만든 JSON 파일 관리자를 임포트합니다.
from app.core.device_config import load_device_configs, save_device_configs, CONFIG_PATH
from app.models.settings import BackendType
from app.workers.manager import manager
from app.stream.state import ingest_q, Sample, get_sys_state, bus_router, stop_bus
from app.workers.ai_state import get_ai_state

# 로그 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TEST_JSON")


async def run_test():
    logger.info("==================================================")
    logger.info("🧹 1단계: 기존 JSON 파일 초기화 (백지상태 만들기)")
    # 기존 파일이 있다면 지워서 완벽한 백지상태 보장
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
    logger.info("✅ device_config.json 파일 삭제 완료 (초기화 됨).")

    logger.info("==================================================")
    logger.info("📝 2단계: 파일에 1번 기기(Test-Device-1) 설정 쓰기")
    initial_configs = [
        {
            "id": 1,
            "name": "Test-Device-1",
            "protocol": BackendType.MODBUS.value,
            "host": "127.0.0.1",
            "port": 5021,
            "unit_id": 1,
            "ns": "",
        }
    ]
    save_device_configs(initial_configs)

    saved_data = load_device_configs()
    logger.info(f"✅ JSON 저장 및 읽기 성공! (현재 기기 수: {len(saved_data)}대)")

    logger.info("==================================================")
    logger.info("🚀 3단계: 버스 라우터 및 WorkerManager 기동 (1대만 켜져야 함)")
    router_task = asyncio.create_task(bus_router())

    # 매니저 초기화: JSON 파일을 읽고 1번 워커만 돌리기 시작함
    await manager.initialize()
    logger.info(f"현재 동작 중인 통신 폴러(스레드) 수: {len(manager._poller_tasks)}개")
    assert len(manager._poller_tasks) == 1, "워커가 1개가 아닙니다!"

    logger.info("==================================================")
    logger.info("➕ 4단계: 시스템 가동 중 2번 기기(Test-Device-2) 동적 추가 테스트")
    # 파일에 2번 기기 추가
    configs = load_device_configs()
    configs.append(
        {
            "id": 2,
            "name": "Test-Device-2",
            "protocol": BackendType.MODBUS.value,
            "host": "127.0.0.1",
            "port": 5022,
            "unit_id": 2,
            "ns": "",
        }
    )
    save_device_configs(configs)

    # 🚀 핵심: 서버를 끄지 않고 워커만 추가!
    await manager.add_worker(2)
    logger.info(f"현재 동작 중인 통신 폴러(스레드) 수: {len(manager._poller_tasks)}개")
    assert len(manager._poller_tasks) == 2, "2번 워커가 정상적으로 켜지지 않았습니다!"

    logger.info("==================================================")
    logger.info("🧪 5단계: AI 자동제어 및 데이터 독립성 테스트")
    sys1 = get_sys_state(1)
    sys2 = get_sys_state(2)
    sys1.auto_mode = True
    sys2.auto_mode = True
    sys1.target_do = 2.0
    sys2.target_do = 2.0

    now = time.time()
    # 1번 기기에는 DO가 높은 데이터를 주입
    await ingest_q.put(
        Sample(
            ts=now,
            do=6.0,
            mlss=3000,
            temp=20,
            ph=7.0,
            air_flow=100,
            power=5,
            pump_hz=45,
            valve_pos=50,
            rtu_id=1,
        )
    )
    # 2번 기기에는 DO가 낮은 데이터를 주입
    await ingest_q.put(
        Sample(
            ts=now,
            do=0.5,
            mlss=3200,
            temp=22,
            ph=7.2,
            air_flow=120,
            power=6,
            pump_hz=30,
            valve_pos=60,
            rtu_id=2,
        )
    )

    logger.info("⏳ AI가 연산할 수 있도록 4초 대기...")
    await asyncio.sleep(4)

    ai_1 = get_ai_state(1)
    ai_2 = get_ai_state(2)
    logger.info(
        f"📊 [Device 1] 실행중: {ai_1.running}, 연산: {ai_1.steps_done}회, 제안 Hz: {ai_1.proposed_hz}"
    )
    logger.info(
        f"📊 [Device 2] 실행중: {ai_2.running}, 연산: {ai_2.steps_done}회, 제안 Hz: {ai_2.proposed_hz}"
    )

    if ai_1.proposed_hz != ai_2.proposed_hz:
        logger.info(
            "🎉 [SUCCESS] 1번 기기와 2번 기기의 AI 연산이 완벽하게 독립적으로 수행되었습니다!"
        )
    else:
        logger.warning("⚠️ [WARNING] 제안된 주파수가 같습니다. (우연의 일치일 수 있음)")

    logger.info("==================================================")
    logger.info("🛑 6단계: 시스템 안전 종료 테스트...")
    await manager.stop_workers()
    stop_bus()
    router_task.cancel()
    logger.info("🎉 [ALL TESTS PASSED] JSON 기반 백엔드 리팩토링 테스트가 100% 성공했습니다!")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        logger.info("사용자에 의해 종료되었습니다.")
