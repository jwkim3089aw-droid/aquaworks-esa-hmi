# app/workers/manager.py
import sys

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr is not None:
    sys.stderr.reconfigure(encoding="utf-8")

import asyncio
import logging
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, Set, Any

# 🚀 중앙 통제식 경로 설정 불러오기
from app.core.config import get_settings
from app.core.device_config import load_device_configs, save_device_configs, get_device_config
from app.models.settings import BackendType
from app.stream.state import command_q, sys_states
from app.workers.db_writer import run_db_writer
from app.workers.modbus_rtu_poller import modbus_poller_loop as rtu_poller_loop
from app.workers.modbus_poller import modbus_poller_loop as tcp_poller_loop
from app.workers.modbus_poller import write_hr_single
from app.workers.opcua_poller import run_opcua_poller
from app.workers.ai_state import get_ai_state

from app.workers.ai.config import SITE, _is_windows, STRICT_DURABILITY
from app.workers.ai.agent import ImmortalAgent
from app.workers.ai.utils import SafetyLayer

settings = get_settings()

# =====================================================================
# 매니저 전용 애플리케이션 이벤트 로거 세팅 (30일 Retention 적용)
# =====================================================================
logger = logging.getLogger("IMMORTAL_AI_MANAGER")
logger.setLevel(logging.INFO)

log_file_path = settings.APP_LOG_DIR / "manager.log"
file_handler = TimedRotatingFileHandler(
    filename=str(log_file_path),
    when="midnight",
    interval=1,
    backupCount=30,
    encoding="utf-8",
)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s")
file_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(file_handler)


class WorkerManager:
    def __init__(self) -> None:
        self._core_tasks: list[asyncio.Task] = []
        self._poller_tasks: Dict[int, asyncio.Task] = {}
        self._bg_tasks: Set[asyncio.Task] = set()

        self._save_inflight = False
        self._fatal_triggered = False
        self._fatal_lock = threading.Lock()

        self.ctrls: Dict[int, ImmortalAgent] = {}

        self.compute_executor = None
        self.io_executor = None
        self._running = False

    def _get_agent(self, rtu_id: int) -> ImmortalAgent:
        """RTU별 독립된 AI 에이전트 인스턴스 반환"""
        if rtu_id not in self.ctrls:
            self.ctrls[rtu_id] = ImmortalAgent(SITE, rtu_id)
        return self.ctrls[rtu_id]

    def _calculate_optimal_valve(
        self, state: Any, target_do: float, curr_do: float, current_valve: float
    ) -> float:
        """🚀 [실전 산업용 밸브 제어 로직 - PI & Deadband & Anti-Windup 적용]"""
        error = target_do - curr_do
        deadband = 0.1  # 정밀 제어를 위해 데드밴드를 축소

        # 1. 데드밴드 이내면 조작 안 함, 오차 누적도 멈춤 (안정성 확보)
        if abs(error) <= deadband:
            return current_valve

        # 2. PI 제어 게인 (현장 상황에 맞게 튜닝)
        Kp = 20.0 if error > 0 else 30.0  # 비례(P) 게인
        Ki = 0.5  # 적분(I) 게인

        # 🚀 [FIX] 3. 오차 누적 (Integral) - 속성 존재 여부 확인 후 초기화
        if not hasattr(state, "error_sum"):
            state.error_sum = 0.0
        state.error_sum += error

        # 4. Anti-windup (적분 누적치 제한: I-term 폭주 방지)
        max_i_term = 30.0
        if (state.error_sum * Ki) > max_i_term:
            state.error_sum = max_i_term / Ki
        elif (state.error_sum * Ki) < -max_i_term:
            state.error_sum = -max_i_term / Ki

        # 5. PI 연산 적용
        p_term = error * Kp
        i_term = state.error_sum * Ki
        target_pos = current_valve + p_term + i_term

        # 6. 밸브 물리적 한계 (0~100%) 제한
        target_pos = max(0.0, min(100.0, target_pos))

        # 7. 기계 보호: 한 번에 움직이는 최대 폭 제한
        max_step = 5.0
        if target_pos > current_valve + max_step:
            return current_valve + max_step
        elif target_pos < current_valve - max_step:
            return current_valve - max_step

        return target_pos

    async def initialize(self) -> None:
        """매니저 초기화 및 코어 스레드/태스크 가동"""
        self._running = True
        self.compute_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="AI_Core")
        self.io_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="IO_Saver")

        if _is_windows and not STRICT_DURABILITY:
            logger.warning("Windows detected: STRICT_DURABILITY defaulted to 0 (warn-only).")

        loop = asyncio.get_running_loop()

        # 🚀 [빅데이터 기반 AI 로깅] 로거 임포트 (예외 처리)
        try:
            from app.workers.ai_logger import run_ai_logger

            ai_logger_task = loop.create_task(run_ai_logger(), name="AILogger")
        except ImportError:
            logger.warning("ai_logger 모듈을 찾을 수 없습니다. AI 빅데이터 로깅이 비활성화됩니다.")
            ai_logger_task = None

        tasks_to_run = [
            loop.create_task(run_db_writer(), name="DBWriter"),
            loop.create_task(self._control_loop(), name="ControlLoop"),
            loop.create_task(self._command_dispatcher_loop(), name="CommandDispatcher"),
        ]
        if ai_logger_task:
            tasks_to_run.append(ai_logger_task)

        self._core_tasks.extend(tasks_to_run)

        configs = load_device_configs()
        for config_dict in configs:
            await self.start_poller(config_dict)
            get_ai_state(config_dict["id"]).update(running=True, fatal=False, last_error=None)

        logger.info(
            f"✅ Immortal AI Manager Started (Loaded {len(configs)} devices). Log Path: {log_file_path}"
        )

    async def add_worker(self, rtu_id: int) -> None:
        config_dict = get_device_config(rtu_id)
        if config_dict:
            await self.start_poller(config_dict)
            get_ai_state(rtu_id).update(running=True, fatal=False, last_error=None)
        else:
            logger.error(f"❌ [Device {rtu_id}] device_config.json 에서 기기를 찾을 수 없습니다.")

    async def update_worker(self, rtu_id: int) -> None:
        await self.add_worker(rtu_id)

    async def start_poller(self, config: dict) -> None:
        rtu_id = config["id"]
        protocol_str = config.get("protocol", BackendType.MODBUS.value)
        host = config.get("host", "127.0.0.1")

        await self.stop_poller(rtu_id)

        loop = asyncio.get_running_loop()
        os.environ[f"ESA_BACKEND_{rtu_id}"] = protocol_str

        task = None
        if protocol_str == BackendType.MODBUS.value:
            host_str = str(host).upper()
            if "COM" in host_str or "/DEV/" in host_str:
                task = loop.create_task(rtu_poller_loop(rtu_id), name=f"Poller_RTU_{rtu_id}")
            else:
                task = loop.create_task(tcp_poller_loop(rtu_id), name=f"Poller_TCP_{rtu_id}")
        elif protocol_str == BackendType.OPCUA.value:
            task = loop.create_task(run_opcua_poller(rtu_id), name=f"Poller_OPC_{rtu_id}")

        if task:
            self._poller_tasks[rtu_id] = task

    async def stop_poller(self, rtu_id: int) -> None:
        if rtu_id in self._poller_tasks:
            task = self._poller_tasks.pop(rtu_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def apply_comm_settings(self, rtu_id: int, port: str, baudrate: int) -> bool:
        configs = load_device_configs()
        found = False
        for c in configs:
            if c["id"] == rtu_id:
                c["host"], c["port"], c["protocol"] = port, baudrate, BackendType.MODBUS.value
                found = True
                break

        if not found:
            configs.append(
                {
                    "id": rtu_id,
                    "name": f"Device-{rtu_id}",
                    "protocol": BackendType.MODBUS.value,
                    "host": port,
                    "port": baudrate,
                    "unit_id": 1,
                    "ns": "",
                }
            )

        save_device_configs(configs)
        await self.add_worker(rtu_id)
        return True

    async def disconnect_comm(self, rtu_id: int) -> None:
        await self.stop_poller(rtu_id)
        configs = load_device_configs()
        for c in configs:
            if c["id"] == rtu_id:
                c["host"] = ""
                break
        save_device_configs(configs)

    async def stop_workers(self) -> None:
        self._running = False
        for rtu_id in list(self._poller_tasks.keys()):
            get_ai_state(rtu_id).update(running=False)
            await self.stop_poller(rtu_id)

        for task in self._core_tasks:
            task.cancel()
        if self._core_tasks:
            await asyncio.gather(*self._core_tasks, return_exceptions=True)
        self._core_tasks.clear()

        if self._bg_tasks:
            await asyncio.gather(*self._bg_tasks, return_exceptions=True)
            self._bg_tasks.clear()

        self.compute_executor.shutdown(wait=True)
        loop = asyncio.get_running_loop()

        for agent in self.ctrls.values():
            try:
                await loop.run_in_executor(self.io_executor, agent.save_checkpoint_task)
            except Exception as e:
                self._fatal_persist(e)
            finally:
                agent.writer.close()

        try:
            self.io_executor.shutdown(wait=True)
        except Exception:
            pass

    def _fatal_persist(self, exc: BaseException) -> None:
        with self._fatal_lock:
            if self._fatal_triggered:
                return
            self._fatal_triggered = True

        for rtu_id in list(self._poller_tasks.keys()) + list(self.ctrls.keys()):
            get_ai_state(rtu_id).update(fatal=True, running=False, last_error=str(exc))

        self._running = False
        for t in self._core_tasks + list(self._poller_tasks.values()):
            t.cancel()

        def _exit_worker():
            try:
                time.sleep(0.2)
            finally:
                os._exit(1)

        threading.Thread(target=_exit_worker, daemon=True).start()

    async def _observe_future(self, fut: asyncio.Future) -> None:
        try:
            await fut
        finally:
            self._save_inflight = False

    def _track_bg_task(self, task: asyncio.Task) -> None:
        self._bg_tasks.add(task)

        def _done(t: asyncio.Task):
            self._bg_tasks.discard(t)
            try:
                exc = t.exception()
            except asyncio.CancelledError:
                return
            if exc:
                self._fatal_persist(exc)

        task.add_done_callback(_done)

    # =====================================================================
    # 🎯 분배기 매핑
    # =====================================================================
    async def _command_dispatcher_loop(self) -> None:
        while self._running:
            try:
                rtu_id, cmd, val = await command_q.get()
                config_dict = get_device_config(rtu_id)
                tags = config_dict.get("tags", {})

                if cmd == "set_hz":
                    addr = tags.get("set_hz", {}).get("mb_addr", 29)
                    await write_hr_single(rtu_id, addr, int(val * 10.0))

                elif cmd == "valve_pos":
                    addr = tags.get("valve_pos", {}).get("mb_addr", 30)
                    await write_hr_single(rtu_id, addr, int(val))

                # 🚀 [FIX] Target DO 명령 처리 분기 추가 (메모리만 업데이트)
                elif cmd == "target_do":
                    from app.stream.state import get_sys_state

                    state = get_sys_state(rtu_id)
                    state.target_do = float(val)

                elif str(cmd).startswith("raw_"):
                    addr = int(str(cmd).split("_")[1])
                    await write_hr_single(rtu_id, addr, int(val))

                elif cmd in tags:
                    addr = tags[cmd].get("mb_addr")
                    if addr is not None:
                        await write_hr_single(rtu_id, addr, int(val))

                command_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Command Dispatch Error: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    # =====================================================================
    # 🎯 로직 격리: 밸브와 AI 펌 제어 완벽 분리
    # =====================================================================
    async def _process_single_rtu(
        self, loop: asyncio.AbstractEventLoop, rtu_id: int, state: Any
    ) -> None:
        agent = self._get_agent(rtu_id)

        # 1. 상태값 로드
        target_do = getattr(state, "target_do", 2.0)
        curr_do = getattr(state, "last_do", 0.0)
        temp = getattr(state, "last_temp", 20.0)
        mlss = getattr(state, "last_mlss", 3000.0)
        ph = getattr(state, "last_ph", 7.0)
        current_valve = getattr(state, "last_valve_pos", 0.0)
        current_hz = getattr(state, "last_hz", 0.0)

        # 2. 밸브 연산 및 하달 (AI와 별개로 100% 동작)
        try:
            target_valve = self._calculate_optimal_valve(state, target_do, curr_do, current_valve)
            await command_q.put((rtu_id, "valve_pos", float(target_valve)))
        except Exception as e:
            logger.error(f"🚨 [RTU {rtu_id}] 밸브 제어 로직 에러: {e}")

        # 3. 펌프 연산 및 하달 (AI 제어)
        try:
            agent.current_hz = current_hz

            ai_proposed_hz = await loop.run_in_executor(
                self.compute_executor, agent.compute, target_do, curr_do, temp, mlss, ph
            )
            target_hz = SafetyLayer.apply_guard(current_hz, ai_proposed_hz, SITE)

            # 🚀 [빅데이터 기반 AI 로깅] 연산이 끝났으므로 큐에 기록 전송
            try:
                from app.stream.state import ai_log_q, AILog

                log_data = AILog(
                    ts=time.time(),
                    rtu_id=rtu_id,
                    target_do=target_do,
                    curr_do=curr_do,
                    temp=temp,
                    mlss=mlss,
                    ph=ph,
                    current_valve=current_valve,
                    current_hz=current_hz,
                    ai_proposed_hz=ai_proposed_hz,
                    final_hz=target_hz,
                )
                ai_log_q.put_nowait(log_data)
            except Exception as log_e:
                logger.error(f"🚨 [AI 로그 저장 실패] 원인: {log_e}")

            await command_q.put((rtu_id, "set_hz", float(target_hz)))
            get_ai_state(rtu_id).update(last_error=None)

            # 성공적인 제어 사이클 로그 (Debug 레벨 등 필요에 따라 조정 가능)
            # logger.debug(f"[RTU {rtu_id}] Control Cycle Complete - Valve: {target_valve:.1f}, Hz: {target_hz:.1f}")

        except Exception as e:
            error_msg = f"AI 모델 연산 에러: {type(e).__name__} - {str(e)}"
            logger.error(f"🚨🚨 [RTU {rtu_id}] {error_msg}")
            logger.error(traceback.format_exc())
            get_ai_state(rtu_id).update(last_error=error_msg)
            await command_q.put((rtu_id, "set_hz", float(current_hz)))

    # =====================================================================
    # 루프 엔진
    # =====================================================================
    async def _control_loop(self) -> None:
        loop = asyncio.get_running_loop()
        save_tick = 0

        while self._running:
            start_time = time.monotonic()
            try:
                for rtu_id, state in sys_states.items():
                    if getattr(state, "auto_mode", False):
                        await self._process_single_rtu(loop, rtu_id, state)

                save_tick += 1
                if save_tick >= 150:
                    if not self._save_inflight:
                        self._save_inflight = True
                        for agent in self.ctrls.values():
                            fut = loop.run_in_executor(self.io_executor, agent.save_checkpoint_task)
                            t = asyncio.create_task(self._observe_future(fut))
                            self._track_bg_task(t)
                    save_tick = 0

                if not any(getattr(s, "auto_mode", False) for s in sys_states.values()):
                    for agent in self.ctrls.values():
                        agent.my_state.update()
                    await asyncio.sleep(1.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Control Loop Error: {e}", exc_info=True)
                await asyncio.sleep(1.0)

            elapsed = time.monotonic() - start_time
            await asyncio.sleep(max(0.1, SITE.dt - elapsed))


manager = WorkerManager()
worker_manager = manager
