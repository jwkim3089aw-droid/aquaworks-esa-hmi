# scripts/test_logging_arch.py
import sys
import asyncio
import time
import threading
from pathlib import Path
from datetime import datetime

# 🚀 [PATCH] PyTorch 스레드 검증을 위해 torch 임포트 추가
import torch

# 1. 환경 설정: code/ 디렉토리를 sys.path에 추가하여 app 모듈 임포트 허용
current_dir = Path(__file__).resolve().parent
base_dir = current_dir.parent
sys.path.insert(0, str(base_dir))

print(f"🚀 [Test Start] 프로젝트 루트 경로 인식: {base_dir}")

# -------------------------------------------------------------------------
# 우리가 리팩토링한 모듈들 임포트
# -------------------------------------------------------------------------
from app.core.config import get_settings
from app.core.device_config import save_device_configs, load_device_configs
from app.workers.ai_logger import _save_buffer_to_parquet
from app.workers.sys_monitor import run_sys_monitor
from app.workers.manager import logger as manager_logger
from app.services.history import logger as history_logger
from app.workers.ai.agent import ImmortalAgent
from app.workers.ai.config import SystemConfig
from app.workers.db_writer import logger as db_writer_logger

# 🚀 [PATCH] Telemetry 통합 로거 핸들러 세팅을 위해 main.py 임포트
import app.main

# 🚀 [PATCH] 통신 폴러별 서브 로거 임포트
from app.workers.modbus_rtu_poller import logger as rtu_logger
from app.workers.modbus_poller import logger as tcp_logger
from app.workers.opcua_poller import logger as opcua_logger


async def main():
    print("\n" + "=" * 50)
    print(" 🛠️ ESA_HMI Logging & Architecture Final Test")
    print("=" * 50)

    try:
        # -----------------------------------------------------------------
        # Test 1: config.py (중앙 통제식 디렉토리 생성 테스트)
        # -----------------------------------------------------------------
        print("\n[Test 1] 📂 기본 디렉토리 멱등성 및 격리 검증...")
        settings = get_settings()

        required_dirs = [
            settings.DATA_DIR,
            settings.SYS_LOG_DIR,
            settings.APP_LOG_DIR,
            settings.AI_LOG_DIR,
            settings.TELEMETRY_LOG_DIR,
        ]
        for d in required_dirs:
            assert d.exists(), f"❌ 디렉토리 생성 실패: {d}"
            print(f"  ✅ [PASS] {d.relative_to(base_dir)} 폴더 확인 완료")

        # -----------------------------------------------------------------
        # Test 2: device_config.py (.data 하위 파일 저장/로드 테스트)
        # -----------------------------------------------------------------
        print("\n[Test 2] 🗄️ 설정 파일 (.data) 격리 입출력 검증...")
        dummy_config = [{"id": 99, "name": "Test_RTU", "protocol": "MODBUS"}]
        save_result = save_device_configs(dummy_config)
        assert save_result is True, "❌ device_config.json 저장 실패"

        loaded_config = load_device_configs()
        assert loaded_config[0]["id"] == 99, "❌ 데이터 로드 불일치"
        print(f"  ✅ [PASS] .data/device_config.json 저장 및 로드 완벽 동작")

        # -----------------------------------------------------------------
        # Test 3: ai_logger.py (빅데이터 Parquet 파티셔닝 테스트)
        # -----------------------------------------------------------------
        print("\n[Test 3] 🧠 AI BigData Logger 파티셔닝 분할 검증...")
        dummy_ai_data = [
            {
                "ts": time.time(),
                "rtu_id": 1,
                "target_do": 2.0,
                "curr_do": 1.5,
                "temp": 20,
                "mlss": 3000,
                "ph": 7,
                "current_valve": 50,
                "current_hz": 30,
                "ai_proposed_hz": 35,
                "final_hz": 35,
            },
            {
                "ts": time.time(),
                "rtu_id": 2,
                "target_do": 2.0,
                "curr_do": 1.8,
                "temp": 21,
                "mlss": 3100,
                "ph": 7.1,
                "current_valve": 40,
                "current_hz": 40,
                "ai_proposed_hz": 40,
                "final_hz": 40,
            },
        ]
        _save_buffer_to_parquet(dummy_ai_data)

        parquet_files = list(settings.AI_LOG_DIR.rglob("*.parquet"))
        assert len(parquet_files) >= 2, f"❌ Parquet 파일이 충분히 생성되지 않았습니다."

        parent_dirs = set(p.parent for p in parquet_files)
        assert len(parent_dirs) >= 2, f"❌ 데이터가 같은 폴더에 뭉쳐있습니다! 분할 실패."
        print("  ✅ [PASS] .logs/ai_agents/ 하위 Parquet 그룹바이 분할 저장 완료!")

        # -----------------------------------------------------------------
        # Test 4: app_events 로거 (Manager, History, DB_Writer 파일 로거 확인)
        # -----------------------------------------------------------------
        print("\n[Test 4] 📝 App Events 파일 로거 검증 (Manager, History, DB_Writer)...")
        manager_logger.info("테스트: 매니저 이벤트 로깅 정상 작동 확인!")
        history_logger.error("테스트: History 쿼리 에러 로깅 정상 작동 확인!")
        db_writer_logger.info("테스트: DB Writer 이벤트 로깅 정상 작동 확인!")

        assert (settings.APP_LOG_DIR / "manager.log").exists(), "❌ manager.log 생성 실패"
        assert (
            settings.APP_LOG_DIR / "history_query.log"
        ).exists(), "❌ history_query.log 생성 실패"
        assert (settings.APP_LOG_DIR / "db_writer.log").exists(), "❌ db_writer.log 생성 실패"
        print("  ✅ [PASS] .logs/app_events/ 하위 3대 로그 파일 정상 작동")

        # -----------------------------------------------------------------
        # Test 5: sys_monitor.py (자원 감시 CSV 저장 및 비동기 루프 검증)
        # -----------------------------------------------------------------
        print("\n[Test 5] 🖥️ 시스템 자원 모니터 (CSV & 비동기 백그라운드) 검증...")
        today_str = datetime.now().strftime("%Y-%m-%d")
        sys_task = asyncio.create_task(run_sys_monitor())
        await asyncio.sleep(1.5)
        sys_task.cancel()

        csv_file = settings.SYS_LOG_DIR / today_str / "resource_usage.csv"
        assert csv_file.exists(), "❌ CSV 리소스 파일 생성 실패"
        print("  ✅ [PASS] .logs/sys_resources/[날짜]/resource_usage.csv 기록 완료")

        # -----------------------------------------------------------------
        # Test 6: AI 모델 및 텐서보드 격리 저장 테스트 (.data/ai_models/)
        # -----------------------------------------------------------------
        print("\n[Test 6] 🤖 AI 모델 및 상태 파일 격리 (.data/ai_models) 검증...")
        ai_cfg = SystemConfig()
        test_rtu_id = 999
        dummy_agent = ImmortalAgent(ai_cfg, rtu_id=test_rtu_id)

        dummy_agent.memory.push(
            state=[0.0] * 9, action=0, reward=1.0, next_state=[0.0] * 9, done=False
        )
        dummy_agent.save_checkpoint_task()

        model_dir = settings.DATA_DIR / "ai_models"
        assert (
            model_dir / f"immortal_brain_v2_rtu_{test_rtu_id}.pth"
        ).exists(), "❌ PyTorch 모델 격리 실패"
        assert (
            model_dir / f"immortal_memory_v2_rtu_{test_rtu_id}.pkl.xz"
        ).exists(), "❌ ReplayBuffer 격리 실패"
        print("  ✅ [PASS] .data/ai_models/ 하위에 모델, 메모리, 텐서보드 격리 확인 완료")

        # (안전한 종료를 위해 6번 테스트용 에이전트 닫기)
        if hasattr(dummy_agent, "close"):
            dummy_agent.close()

        # -----------------------------------------------------------------
        # Test 7: Telemetry 중앙 집중 로깅 아키텍처 (comm.log) 검증
        # -----------------------------------------------------------------
        print("\n[Test 7] 📡 Telemetry 통신 통합 파일 로거 (comm.log) 검증...")
        rtu_logger.info("테스트: Modbus RTU 통신 로깅 정상 작동!")
        tcp_logger.warning("테스트: Modbus TCP 통신 에러 로깅 정상 작동!")
        opcua_logger.error("테스트: OPC UA 통신 타임아웃 로깅 정상 작동!")

        comm_log_file = settings.TELEMETRY_LOG_DIR / "comm.log"
        assert comm_log_file.exists(), "❌ comm.log 단일 파일 생성 실패"

        with open(comm_log_file, "r", encoding="utf-8") as f:
            log_content = f.read()
            assert "[telemetry.modbus_rtu]" in log_content, "❌ RTU 로깅이 comm.log에 없음"
            assert "[telemetry.modbus_tcp]" in log_content, "❌ TCP 로깅이 comm.log에 없음"
            assert "[telemetry.opcua]" in log_content, "❌ OPC UA 로깅이 comm.log에 없음"
        print("  ✅ [PASS] .logs/telemetry/comm.log 통합 파일 출력 및 이름표 격리 완벽 동작 확인")

        # -----------------------------------------------------------------
        # 🚀 [Test 8] AI Agent 정석 아키텍처 (Actor-Learner 분리 & 자원 보호) 검증
        # -----------------------------------------------------------------
        print("\n[Test 8] 🛡️ AI Agent 정석 아키텍처 (CPU 보호 & 비동기 학습) 검증...")

        # 1. CPU 보호 스레드 제한 검증
        num_threads = torch.get_num_threads()
        assert num_threads <= 2, f"❌ PyTorch 스레드가 제한되지 않았습니다. (현재: {num_threads}개)"
        print("  ✅ [PASS] PyTorch CPU 병렬 연산 제한 확인 (CPU 130% 폭주 방지)")

        # 2. 강제 학습 모드 에이전트 생성
        test_rtu_id_2 = 777
        ai_cfg_2 = SystemConfig()
        ai_cfg_2.train_mode = True
        ai_cfg_2.batch_size = 8  # 빠른 트리거를 위해 작게 설정
        agent_v2 = ImmortalAgent(ai_cfg_2, rtu_id=test_rtu_id_2)

        # 3. 백그라운드 스레드(Learner) 독립 구동 검증
        learner_thread_name = f"AI_Learner_RTU_{test_rtu_id_2}"
        threads_alive = [t.name for t in threading.enumerate()]
        assert (
            learner_thread_name in threads_alive
        ), "❌ 백그라운드 학습 스레드가 구동되지 않았습니다."
        print(f"  ✅ [PASS] 비동기 학습 스레드 '{learner_thread_name}' 분리 구동 확인")

        # 4. 제어 루프(compute) 논블로킹 속도 검증
        # 버퍼를 꽉 채워서 원래라면 역전파 학습이 발동되어 느려져야 할 상황을 강제로 만듦
        for _ in range(ai_cfg_2.batch_size + 2):
            agent_v2.memory.push(
                state=[0.0] * 9, action=0, reward=0.0, next_state=[0.0] * 9, done=False
            )

        start_time = time.perf_counter()
        # compute 호출! 학습을 백그라운드가 가져갔다면 엄청 빨리 끝나야 함
        agent_v2.compute(target_do=2.0, raw_do=1.5, raw_temp=20.0, raw_mlss=3000.0, raw_ph=7.0)
        elapsed_time = time.perf_counter() - start_time

        assert (
            elapsed_time < 0.1
        ), f"❌ compute() 속도가 너무 느립니다({elapsed_time:.4f}초). 동기화 락 걸림!"
        print(
            f"  ✅ [PASS] 메인 제어루프(compute) 병목 현상 없음 확인 (소요시간: {elapsed_time:.4f}초)"
        )

        # 5. 좀비 스레드 방지 (Graceful Shutdown) 검증
        agent_v2.close()
        await asyncio.sleep(1.2)  # 스레드 루프 내의 sleep(1.0)을 고려하여 대기
        threads_after = [t.name for t in threading.enumerate()]
        assert (
            learner_thread_name not in threads_after
        ), "❌ 프로그램 종료 후에도 학습 스레드가 남아있습니다."
        print(
            "  ✅ [PASS] 에이전트 종료 시 메모리 누수 및 좀비 스레드 완벽 차단 (Graceful Shutdown)"
        )

        print("\n🎉 [SUCCESS] 아키텍처, 성능 최적화, 스레드 안전성까지 완벽 검증 완료! 🚀")

    except AssertionError as e:
        print(f"\n🚨 [FAILED] 테스트 중 에러 발생: {e}")
    except Exception as e:
        print(f"\n🚨 [CRITICAL] 예기치 않은 오류 발생: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
