# app/workers/sys_monitor.py
import asyncio
import logging
import csv
import shutil
import os
import time
import tracemalloc  # 👈 메모리 추적을 위해 추가
from datetime import datetime, timedelta
import psutil

from app.core.config import get_settings

logger = logging.getLogger("SYS_MONITOR")
logger.setLevel(logging.INFO)

settings = get_settings()
LOG_DIR = settings.SYS_LOG_DIR

MONITOR_INTERVAL = 60.0
RETENTION_DAYS = 30
MEMORY_WARN_THRESHOLD_MB = 3000.0


def _cleanup_old_logs():
    now = datetime.now()
    cutoff_date = now - timedelta(days=RETENTION_DAYS)
    if not LOG_DIR.exists():
        return

    for path in LOG_DIR.iterdir():
        if path.is_dir():
            try:
                if datetime.strptime(path.name, "%Y-%m-%d") < cutoff_date:
                    shutil.rmtree(path)
                    logger.info(f"🧹 [Retention] 30일 경과 로그 삭제 완료: {path.name}")
            except Exception:
                pass


async def run_sys_monitor():
    logger.info(f"🖥️ Ultimate System & Health Monitor Started. (Saving to {LOG_DIR.as_posix()})")

    process = psutil.Process(os.getpid())
    core_count = psutil.cpu_count(logical=True)
    process.cpu_percent()

    last_cleanup_date = None

    # 🕵️‍♂️ 1. 메모리 추적(tracemalloc) 시작 및 초기 상태 스냅샷 저장
    tracemalloc.start(10)
    baseline_snapshot = tracemalloc.take_snapshot()

    while True:
        try:
            # ⏱️ 2. 이벤트 루프 지연(Lag) 측정
            loop_start = time.perf_counter()
            await asyncio.sleep(0.1)
            loop_lag_ms = (time.perf_counter() - loop_start - 0.1) * 1000.0  # ms 단위 지연 시간

            now = datetime.now()
            current_date = now.strftime("%Y-%m-%d")
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

            # ⚙️ 3. 하드웨어/OS 3대장 (CPU, Mem, Disk)
            sys_cpu = psutil.cpu_percent(interval=0.0)
            raw_proc_cpu = process.cpu_percent(interval=0.0)
            norm_proc_cpu = raw_proc_cpu / core_count if core_count else raw_proc_cpu
            mem_usage_mb = process.memory_info().rss / (1024 * 1024)

            disk_info = psutil.disk_usage(os.path.abspath(LOG_DIR))
            disk_usage_percent = disk_info.percent
            disk_free_gb = disk_info.free / (1024**3)

            # 🦠 4. 파이썬 내부 암살자 2대장 (스레드 누수, 파일 핸들 누수)
            thread_count = process.num_threads()
            try:
                handle_count = process.num_handles() if os.name == "nt" else process.num_fds()
            except AttributeError:
                handle_count = 0

            # 📝 날짜별 디렉토리 준비
            date_dir = LOG_DIR / current_date
            date_dir.mkdir(parents=True, exist_ok=True)

            # 🚨 5. 메모리 임계치 초과 시 범인 색출 및 로그 저장
            if mem_usage_mb > MEMORY_WARN_THRESHOLD_MB:
                logger.warning(
                    f"⚠️ 메모리 경고치 초과! ({mem_usage_mb:.1f} MB) 누수 분석 기록을 시작합니다."
                )

                current_snapshot = tracemalloc.take_snapshot()
                top_stats = current_snapshot.compare_to(baseline_snapshot, "lineno")

                trace_file = date_dir / "memory_trace.txt"

                with open(trace_file, mode="a", encoding="utf-8") as tf:
                    tf.write(f"\n========================================\n")
                    tf.write(f"[{timestamp}] ⚠️ Memory Alert: {mem_usage_mb:.1f} MB\n")
                    tf.write(f"Top 10 Memory Allocations:\n")
                    tf.write(f"----------------------------------------\n")
                    for stat in top_stats[:10]:
                        tf.write(f"{stat}\n")
                        logger.warning(stat)  # 터미널에도 함께 출력

            # 📝 6. 시스템 자원 CSV 기록
            csv_file = date_dir / "resource_usage.csv"
            file_exists = csv_file.exists()

            with open(csv_file, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(
                        [
                            "Timestamp",
                            "System_CPU(%)",
                            "HMI_CPU(%)",
                            "HMI_Memory(MB)",
                            "Disk_Usage(%)",
                            "Disk_Free(GB)",
                            "Thread_Count",
                            "File_Handles",
                            "Loop_Lag(ms)",
                        ]
                    )
                writer.writerow(
                    [
                        timestamp,
                        f"{sys_cpu:.1f}",
                        f"{norm_proc_cpu:.1f}",
                        f"{mem_usage_mb:.1f}",
                        f"{disk_usage_percent:.1f}",
                        f"{disk_free_gb:.1f}",
                        thread_count,
                        handle_count,
                        f"{max(0, loop_lag_ms):.1f}",
                    ]
                )

            # 🧹 7. Retention (과거 로그 정리)
            if last_cleanup_date != current_date:
                _cleanup_old_logs()
                last_cleanup_date = current_date

        except Exception as e:
            logger.error(f"System Monitor Error: {e}")

        # 측정 주기를 맞추기 위해 60초에서 앞서 대기한 0.1초를 빼고 대기
        await asyncio.sleep(MONITOR_INTERVAL - 0.1)
