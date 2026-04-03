# app/workers/ai_logger.py
import asyncio
import logging
import time
from datetime import datetime
import pandas as pd

from app.stream.state import ai_log_q, AILog
from app.core.config import get_settings  # 🚀 중앙 설정 불러오기

logger = logging.getLogger("AI_LOGGER")
logger.setLevel(logging.INFO)

# 1. config.py에서 정의한 AI 로그 전용 경로(pathlib.Path) 가져오기
settings = get_settings()
LOG_DIR = settings.AI_LOG_DIR

# 🚀 1시간 단위 저장 설정
BATCH_SIZE = 10000
FLUSH_INTERVAL = 3600.0


def _save_buffer_to_parquet(buffer_data: list):
    """메모리에 모인 버퍼를 장비별(rtu_id)로 분류하여 Parquet 파일로 저장"""
    if not buffer_data:
        return

    try:
        df = pd.DataFrame(buffer_data)

        # 공통 날짜 및 타임스탬프
        current_date = datetime.now().strftime("%Y-%m-%d")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 🚀 2. Pandas groupby로 rtu_id별로 데이터를 찢기!
        for rtu_id, group_df in df.groupby("rtu_id"):
            # 3. pathlib을 이용한 우아한 경로 병합 및 디렉토리 생성
            # 🚀 변경된 경로: .logs/ai_agents/RTU_1/2026-03-16/ (기기 -> 날짜 순으로 뒤집기 완료!)
            rtu_dir = LOG_DIR / f"RTU_{int(rtu_id)}" / current_date
            rtu_dir.mkdir(parents=True, exist_ok=True)

            # 파일명 생성 및 최종 경로 조합
            filename = f"ai_log_RTU_{int(rtu_id)}_{timestamp_str}.parquet"
            filepath = rtu_dir / filename

            # 4. Pandas는 pathlib.Path 객체를 기본 지원하므로 그대로 전달
            group_df.to_parquet(filepath, index=False)

        logger.info(
            f"💾 AI 로그 장비별 분할 저장 완료: [기기]/[날짜] 구조 (총 {len(buffer_data)}건)"
        )

    except Exception as e:
        logger.error(f"Parquet Save Error: {e}")


async def run_ai_logger():
    # 경로 출력 시 as_posix()를 사용하여 운영체제 무관하게 깔끔한 슬래시(/) 문자열 출력
    logger.info(f"🚀 AI BigData Logger Started. (Saving to {LOG_DIR.as_posix()})")

    buffer = []
    last_flush = time.time()

    while True:
        try:
            log_item: AILog = await asyncio.wait_for(ai_log_q.get(), timeout=1.0)
            buffer.append(log_item.__dict__)
            ai_log_q.task_done()

        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            logger.info("🛑 AI Logger Stopped. 메모리에 남은 데이터를 파일로 백업합니다...")
            _save_buffer_to_parquet(buffer)
            break
        except Exception as e:
            logger.error(f"AI Log Queue Error: {e}")

        now = time.time()
        # 버퍼가 꽉 찼거나, 플러시 주기가 도래했을 때 저장
        if len(buffer) >= BATCH_SIZE or (len(buffer) > 0 and now - last_flush >= FLUSH_INTERVAL):
            _save_buffer_to_parquet(buffer)
            buffer.clear()
            last_flush = now
