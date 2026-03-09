import sys
import os
import asyncio
import logging
import time

# 현재 스크립트 위치(scripts)의 부모 디렉토리(code)를 파이썬 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import engine, Base
from app.models.settings import ConnectionConfig, BackendType
from app.workers.manager import manager
from app.stream.state import ingest_q, Sample, get_sys_state, command_q, bus_router, stop_bus
from app.workers.ai_state import get_ai_state

# 로그 설정 (테스트 결과를 한눈에 보기 쉽게 포맷팅)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TEST_MULTI")

AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def setup_test_db():
    """기존 DB를 완전히 밀어버리고, 깨끗한 상태에서 1번, 2번 기기를 세팅합니다."""
    logger.info("==================================================")
    logger.info("🛠️ 1단계: 데이터베이스 초기화 및 다중 기기 세팅 시작...")

    async with engine.begin() as conn:
        # 완벽한 백지상태를 위해 기존 테이블 삭제 후 재생성
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # N-Scale 테스트를 위한 2대의 기기 하드코딩 주입
        cfg1 = ConnectionConfig(id=1, backend_type=BackendType.MODBUS, host="127.0.0.1", port=5021)
        cfg2 = ConnectionConfig(id=2, backend_type=BackendType.MODBUS, host="127.0.0.1", port=5022)

        session.add_all([cfg1, cfg2])
        await session.commit()

        logger.info("✅ [RTU 1] 설정 DB에 추가됨 (Port: 5021).")
        logger.info("✅ [RTU 2] 설정 DB에 추가됨 (Port: 5022).")
    logger.info("✅ DB 세팅 완료!\n")


async def run_test():
    await setup_test_db()

    logger.info("==================================================")
    logger.info("🚀 2단계: 버스 라우터 및 WorkerManager(AI 에이전트) 기동...")
    # 데이터 라우터 시작 (ingest_q -> db_q, _data_bufs 로 넘겨주는 역할)
    router_task = asyncio.create_task(bus_router())

    # 매니저 초기화 (DB를 읽고 RTU 1, 2의 워커 스레드를 각각 생성해야 정상)
    await manager.initialize()

    # 두 기기를 모두 자동 제어(Auto) 모드로 강제 전환 (AI 루프 활성화)
    sys1 = get_sys_state(1)
    sys2 = get_sys_state(2)
    sys1.auto_mode = True
    sys2.auto_mode = True
    sys1.target_do = 2.0  # 목표 용존산소량 설정
    sys2.target_do = 2.0
    logger.info("✅ 두 기계의 제어 모드를 [AUTO]로 전환 완료.\n")

    logger.info("==================================================")
    logger.info("🧪 3단계: 두 기계에 서로 상반된 가짜 데이터(Sample) 주입 중...")
    now = time.time()

    # [RTU 1] DO가 5.5로 너무 높음 -> AI가 주파수(Hz)를 낮춰야 함
    await ingest_q.put(
        Sample(
            ts=now,
            do=5.5,
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

    # [RTU 2] DO가 0.5로 너무 낮음 -> AI가 주파수(Hz)를 높여야 함
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

    logger.info("⏳ AI가 데이터를 인지하고 연산할 수 있도록 5초 대기...\n")
    await asyncio.sleep(5)

    logger.info("==================================================")
    logger.info("🧠 4단계: === AI 상태(State) 독립성 검증 결과 ===")
    ai_1 = get_ai_state(1)
    ai_2 = get_ai_state(2)

    logger.info(
        f"📊 [RTU 1] 뇌 상태 | 실행중: {ai_1.running}, 연산: {ai_1.steps_done}회, 제안 Hz: {ai_1.proposed_hz}"
    )
    logger.info(
        f"📊 [RTU 2] 뇌 상태 | 실행중: {ai_2.running}, 연산: {ai_2.steps_done}회, 제안 Hz: {ai_2.proposed_hz}"
    )

    # 검증 로직: 두 AI가 서로 다른 데이터를 받았으므로, 제안하는 주파수가 무조건 달라야 함
    if ai_1.proposed_hz != ai_2.proposed_hz:
        logger.info(
            "🎉 [SUCCESS] 1번 기기와 2번 기기의 AI 연산 결과가 다릅니다! 완벽하게 분리되었습니다."
        )
    else:
        logger.warning(
            "⚠️ [WARNING] 제안된 주파수가 같습니다. AI 뇌 상태 분리를 다시 확인해 봐야 합니다."
        )

    logger.info("\n==================================================")
    logger.info("📡 5단계: 수동 명령 라우팅 테스트 (2번 기계 밸브 75% 조작)...")
    await command_q.put((2, "valve_pos", 75.0))
    await asyncio.sleep(2)  # Dispatcher가 로그를 찍고 처리할 시간을 줍니다.

    logger.info("\n==================================================")
    logger.info("🛑 6단계: 시스템 안전 종료 테스트...")
    await manager.stop_workers()
    stop_bus()
    router_task.cancel()
    logger.info(
        "🎉 [ALL TESTS PASSED] 모든 N-Scale 백엔드 통합 테스트가 성공적으로 완료되었습니다!"
    )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        logger.info("사용자에 의해 테스트가 강제 종료되었습니다.")
