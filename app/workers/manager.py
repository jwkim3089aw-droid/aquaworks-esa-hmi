# app/workers/manager.py

"""
Omega Grade v2 (Disk-Safe, Operationally Honest, Windows-Compatible) + N-Scale Multi-Device Ready (JSON File-based)
"""

import asyncio
import logging
import os
import random
import shutil
import sys
import threading
import time
import pickle
import lzma
import math
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional, Set, Dict

import torch
import torch.nn as nn
import torch.optim as optim
from pydantic import BaseModel, Field
from torch.utils.tensorboard import SummaryWriter

# 🚀 [NEW] DB 임포트를 걷어내고 JSON 파일 관리자를 임포트합니다.
from app.core.device_config import load_device_configs, save_device_configs, get_device_config
from app.models.settings import BackendType

from app.stream.state import command_q, sys_states, get_sys_state
from app.workers.db_writer import run_db_writer
from app.workers.modbus_rtu_poller import modbus_poller_loop as rtu_poller_loop
from app.workers.modbus_poller import modbus_poller_loop as tcp_poller_loop
from app.workers.modbus_poller import write_hr_single
from app.workers.opcua_poller import run_opcua_poller

from app.workers.ai_state import ai_state
from app.workers.ai_state import get_ai_state


# -----------------------------------------------------------------------------
# 0. GLOBAL CONFIGURATION
# -----------------------------------------------------------------------------
logger = logging.getLogger("IMMORTAL_AI")
logger.setLevel(logging.INFO)

BASE_PATH = Path(__file__).resolve().parent
DATA_DIR = BASE_PATH / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_is_windows = os.name == "nt"
_default_strict = "0" if _is_windows else "1"

STRICT_DURABILITY = os.getenv("STRICT_DURABILITY", _default_strict) == "1"
STRICT_DIRSYNC = os.getenv("STRICT_DIRSYNC", "1") == "1"

if _is_windows and STRICT_DURABILITY:
    raise RuntimeError(
        "STRICT_DURABILITY=1 on Windows cannot guarantee DB-grade durability. "
        "Set STRICT_DURABILITY=0 or run on POSIX filesystem."
    )


class SystemConfig(BaseModel):
    name: str = "ESA_Final_Product"
    air_start_hz: float = Field(default=28.0, ge=0.0, le=60.0)
    min_hz: float = Field(default=15.0, ge=0.0)
    max_hz: float = Field(default=50.0, ge=0.0, le=60.0)
    dt: float = 2.0
    base_valve_pos: float = 80.0
    batch_size: int = 64
    memory_capacity: int = 50000
    learning_rate: float = 0.0003
    train_mode: bool = True


SITE = SystemConfig()


# -----------------------------------------------------------------------------
# 1. UTILS & SAFETY helpers (Numpy Free)
# -----------------------------------------------------------------------------
def _safe_float_opt(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None or isinstance(x, bool):
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _safe_float(x: Any, default: float) -> float:
    v = _safe_float_opt(x, default=None)
    return v if v is not None else default


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _unique_suffix() -> str:
    return f"{os.getpid()}.{time.time_ns()}.{random.getrandbits(32):08x}"


def _unique_tmp(path: Path) -> Path:
    return path.with_name(f"{path.name}.tmp.{_unique_suffix()}")


def _unique_corrupt(path: Path) -> Path:
    return path.with_name(f"{path.name}.corrupt.{_unique_suffix()}")


def _fsync_fd(fd: int) -> None:
    try:
        os.fsync(fd)
    except Exception:
        if STRICT_DURABILITY:
            raise


def _fsync_path_ro(path: Path) -> None:
    fd = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= getattr(os, "O_CLOEXEC")
        fd = os.open(str(path), flags)
        os.fsync(fd)
    except Exception:
        if STRICT_DURABILITY:
            raise
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass


def _fsync_dir(target_path: Path) -> None:
    if os.name == "nt":
        return
    parent = target_path.parent
    if not parent.is_dir():
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= getattr(os, "O_DIRECTORY")
    if hasattr(os, "O_CLOEXEC"):
        flags |= getattr(os, "O_CLOEXEC")
    fd = None
    try:
        fd = os.open(str(parent), flags)
        os.fsync(fd)
    except Exception:
        if STRICT_DURABILITY and STRICT_DIRSYNC:
            raise
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass


def _atomic_replace_with_barriers(tmp: Path, dst: Path) -> None:
    os.replace(tmp, dst)
    _fsync_path_ro(dst)
    _fsync_dir(dst)


def _gc_files(dir_path: Path, pattern: str, older_than_sec: int = 7 * 24 * 3600) -> None:
    try:
        now = time.time()
        for p in dir_path.glob(pattern):
            try:
                if not p.is_file():
                    continue
                if older_than_sec <= 0:
                    p.unlink()
                else:
                    if now - p.stat().st_mtime > older_than_sec:
                        p.unlink()
            except Exception:
                pass
    except Exception:
        pass


def _durable_backup(src: Path, bak: Path) -> None:
    tmp = _unique_tmp(bak)
    try:
        with open(src, "rb") as r, open(tmp, "wb") as w:
            shutil.copyfileobj(r, w)
            w.flush()
            _fsync_fd(w.fileno())
        _fsync_path_ro(tmp)
        _atomic_replace_with_barriers(tmp, bak)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise


def _save_torch_atomic(dst: Path, obj: dict) -> None:
    tmp = _unique_tmp(dst)
    try:
        with open(tmp, "wb") as f:
            torch.save(obj, f)
            f.flush()
            _fsync_fd(f.fileno())
        _fsync_path_ro(tmp)
        _atomic_replace_with_barriers(tmp, dst)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise


def _save_lzma_pickle_atomic(dst: Path, data: Any) -> None:
    tmp = _unique_tmp(dst)
    try:
        with open(tmp, "wb") as raw:
            with lzma.open(raw, "wb") as zf:
                pickle.dump(data, zf)
                zf.flush()
            raw.flush()
            _fsync_fd(raw.fileno())
        _fsync_path_ro(tmp)
        _atomic_replace_with_barriers(tmp, dst)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise


class EMAFilter:
    __slots__ = ("alpha", "value")

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.value: Optional[float] = None

    def update(self, new_val: Optional[float]) -> float:
        safe_val = _safe_float_opt(new_val, default=None)
        if safe_val is None:
            return self.value if self.value is not None else 0.0
        if self.value is None:
            self.value = safe_val
        else:
            self.value = self.alpha * safe_val + (1 - self.alpha) * self.value
        return self.value


class SafetyLayer:
    @staticmethod
    def apply_guard(
        target_do: float, current_do: float, proposed_hz: float, config: SystemConfig
    ) -> float:
        safe_hz = max(config.min_hz, min(config.max_hz, proposed_hz))
        if target_do > 0.5 and current_do < 0.5:
            if safe_hz < 35.0:
                return 35.0
        if current_do > target_do + 0.5:
            if safe_hz > config.air_start_hz + 5.0:
                safe_hz -= 1.0
        return safe_hz


# -----------------------------------------------------------------------------
# 2. NEURAL NETWORK & MEMORY
# -----------------------------------------------------------------------------
class DuelingQNetwork(nn.Module):
    def __init__(self, state_dim: int, action_dim: int):
        super().__init__()
        self.feature_layer = nn.Sequential(
            nn.Linear(state_dim, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
        )
        self.value_stream = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 1))
        self.advantage_stream = nn.Sequential(
            nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, action_dim)
        )
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(m):
        if isinstance(m, nn.Linear):
            nn.init.kaiming_normal_(m.weight, nonlinearity="relu")

    def forward(self, x):
        features = self.feature_layer(x)
        values = self.value_stream(features)
        advantages = self.advantage_stream(features)
        return values + (advantages - advantages.mean(dim=1, keepdim=True))


class ReplayBuffer:
    def __init__(self, capacity: int = 50000, state_dim: int = 8):
        self.buffer = deque(maxlen=capacity)
        self.state_dim = int(state_dim)

    @staticmethod
    def _to_float_list(x) -> list[float]:
        if x is None:
            return []
        if torch.is_tensor(x):
            x = x.detach().cpu().tolist()
        if isinstance(x, (int, float)):
            return [float(x)]
        try:
            return [float(v) for v in list(x)]
        except Exception:
            return []

    def _sanitize_transition(self, item):
        try:
            s, a, r, ns, d = item
            s = self._to_float_list(s)
            ns = self._to_float_list(ns)
            if len(s) != self.state_dim or len(ns) != self.state_dim:
                return None
            return (s, int(a), float(r), ns, float(bool(d)))
        except Exception:
            return None

    def push(self, state, action, reward, next_state, done) -> None:
        s = self._to_float_list(state)
        ns = self._to_float_list(next_state)
        if len(s) != self.state_dim or len(ns) != self.state_dim:
            return
        self.buffer.append((s, int(action), float(reward), ns, float(bool(done))))

    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, batch_size)
        states = [b[0] for b in batch]
        actions = [b[1] for b in batch]
        rewards = [b[2] for b in batch]
        next_states = [b[3] for b in batch]
        dones = [b[4] for b in batch]
        return states, actions, rewards, next_states, dones

    def __len__(self) -> int:
        return len(self.buffer)

    def save_memory_compressed(self, path: Path, snapshot=None) -> None:
        _save_lzma_pickle_atomic(path, snapshot if snapshot is not None else self.buffer)

    def load_memory_compressed(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            with lzma.open(path, "rb") as f:
                raw = pickle.load(f)
            loaded, dropped = 0, 0
            for item in raw:
                sani = self._sanitize_transition(item)
                if sani is None:
                    dropped += 1
                    continue
                self.buffer.append(sani)
                loaded += 1
            logger.info("📂 Memory Loaded: %d items. (dropped=%d)", loaded, dropped)
        except Exception:
            try:
                corrupt = _unique_corrupt(path)
                os.replace(path, corrupt)
                _fsync_dir(corrupt)
            except Exception:
                pass


# -----------------------------------------------------------------------------
# 3. IMMORTAL AGENT
# -----------------------------------------------------------------------------
class ImmortalAgent:
    def __init__(self, config: SystemConfig, rtu_id: int):
        self.cfg = config
        self.rtu_id = rtu_id

        self.brain_path = DATA_DIR / f"immortal_brain_v2_rtu_{self.rtu_id}.pth"
        self.memory_path = DATA_DIR / f"immortal_memory_v2_rtu_{self.rtu_id}.pkl.xz"

        self.state_dim = 8
        self.my_state = get_ai_state(self.rtu_id)
        self.action_map = [-2.0, -1.0, -0.5, -0.1, 0.0, 0.1, 0.5, 1.0, 2.0]
        self.action_dim = len(self.action_map)
        self.device = torch.device("cpu")
        self._lock = threading.RLock()

        self.policy_net = DuelingQNetwork(self.state_dim, self.action_dim).to(self.device)
        self.target_net = DuelingQNetwork(self.state_dim, self.action_dim).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.AdamW(self.policy_net.parameters(), lr=self.cfg.learning_rate)
        self.memory = ReplayBuffer(capacity=self.cfg.memory_capacity, state_dim=self.state_dim)

        self.memory.load_memory_compressed(self.memory_path)
        self.gamma = 0.98
        self.tau = 0.005
        self.epsilon = 1.0
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.9995

        self.integral_error = 0.0
        self.history = deque(maxlen=10)
        self.last_state = None
        self.last_action_idx = None
        self.current_hz = 30.0
        self.steps_done = 0

        self.filter_do = EMAFilter(alpha=0.4)
        self.filter_temp = EMAFilter(alpha=0.1)
        self.writer = SummaryWriter(log_dir=str(DATA_DIR / f"runs_rtu_{self.rtu_id}"))

        self._load_brain()

        self.my_state.update(
            action_map=[float(x) for x in self.action_map],
            train_mode=self.cfg.train_mode,
            steps_done=int(self.steps_done),
            epsilon=float(self.epsilon if self.cfg.train_mode else 0.0),
        )

    def _load_brain(self) -> None:
        if not self.brain_path.exists():
            return
        try:
            checkpoint = torch.load(self.brain_path, map_location=self.device)
            state_dict, opt_state, version = None, None, None

            if isinstance(checkpoint, dict) and "model_state" in checkpoint:
                version = checkpoint.get("version", None)
                state_dict = checkpoint["model_state"]
                self.steps_done = int(checkpoint.get("steps_done", 0))
                self.epsilon = float(checkpoint.get("epsilon", 1.0))
                opt_state = checkpoint.get("optimizer_state", None)
            else:
                state_dict = checkpoint
                self.steps_done = int(len(self.memory))
                self.epsilon = float(self.epsilon_min)
                migrated_data = {
                    "version": 2,
                    "model_state": state_dict,
                    "optimizer_state": self.optimizer.state_dict(),
                    "steps_done": self.steps_done,
                    "epsilon": self.epsilon,
                }
                try:
                    if self.brain_path.exists():
                        _durable_backup(
                            self.brain_path,
                            self.brain_path.with_suffix(self.brain_path.suffix + ".bak_legacy"),
                        )
                    _save_torch_atomic(self.brain_path, migrated_data)
                except Exception:
                    pass
                opt_state, version = None, 2

            if state_dict:
                current_dict = self.policy_net.state_dict()
                try:
                    if (
                        state_dict["feature_layer.0.weight"].shape
                        != current_dict["feature_layer.0.weight"].shape
                    ):
                        old_dim = self.brain_path.with_name(self.brain_path.name + ".old_dim")
                        shutil.move(self.brain_path, old_dim)
                        try:
                            _fsync_dir(old_dim)
                        except Exception:
                            pass
                        return
                except Exception:
                    return

                self.policy_net.load_state_dict(state_dict)
                self.target_net.load_state_dict(state_dict)

                if opt_state is not None:
                    try:
                        self.optimizer.load_state_dict(opt_state)
                    except Exception:
                        pass
        except Exception:
            pass

    def save_checkpoint_task(self) -> None:
        self.my_state.update(save_inflight=True)
        try:
            _gc_files(DATA_DIR, f"{self.brain_path.name}.tmp.*", older_than_sec=0)
            _gc_files(DATA_DIR, f"{self.memory_path.name}.tmp.*", older_than_sec=0)
            bak_name = self.brain_path.name + ".bak"
            _gc_files(DATA_DIR, f"{bak_name}.tmp.*", older_than_sec=0)

            with self._lock:
                cpu_weights = {
                    k: v.detach().cpu().clone() for k, v in self.policy_net.state_dict().items()
                }
                checkpoint_data = {
                    "version": 2,
                    "model_state": cpu_weights,
                    "optimizer_state": self.optimizer.state_dict(),
                    "steps_done": int(self.steps_done),
                    "epsilon": float(self.epsilon),
                }
                mem_snapshot = list(self.memory.buffer) if self.cfg.train_mode else None

            if self.brain_path.exists():
                _durable_backup(self.brain_path, self.brain_path.with_name(bak_name))
            _save_torch_atomic(self.brain_path, checkpoint_data)

            if mem_snapshot is not None:
                self.memory.save_memory_compressed(self.memory_path, snapshot=mem_snapshot)

            self.my_state.update(last_save_ts=time.time(), last_save_ok=True)
        except Exception as e:
            self.my_state.update(last_save_ok=False, last_error=str(e))
            raise
        finally:
            self.my_state.update(save_inflight=False)

    def get_state_vector(self, target_do, current_do, temp, mlss, ph) -> list[float]:
        error = target_do - current_do
        self.history.append(current_do)
        slope = self.history[-1] - self.history[0] if len(self.history) >= 3 else 0.0
        self.integral_error = _clamp(self.integral_error + error, -10.0, 10.0)

        raw_state = [
            error,
            slope * 5.0,
            self.integral_error / 10.0,
            (self.current_hz - 30.0) / 20.0,
            (temp - 20.0) / 10.0,
            (mlss - 3000.0) / 2000.0,
            (ph - 7.0) / 2.0,
            1.0 if target_do > current_do else -1.0,
        ]
        return [float(v) if math.isfinite(v) else 0.0 for v in raw_state]

    def select_action(self, state_vec: list[float]) -> int:
        self.steps_done += 1
        current_epsilon = float(self.epsilon if self.cfg.train_mode else 0.0)
        self.my_state.update(epsilon=current_epsilon, steps_done=int(self.steps_done))

        with torch.no_grad():
            state_tensor = torch.tensor(
                state_vec, dtype=torch.float32, device=self.device
            ).unsqueeze(0)
            q_vals = self.policy_net(state_tensor)
            q_vals_list = [float(x) for x in q_vals.squeeze(0).detach().cpu().tolist()]

        if self.cfg.train_mode and random.random() < current_epsilon:
            action = random.randint(0, self.action_dim - 1)
        else:
            action = int(q_vals.argmax(dim=1).item())

        self.my_state.update(q_values=q_vals_list)
        return action

    def update_model(self) -> None:
        if len(self.memory) < self.cfg.batch_size:
            return
        states, actions, rewards, next_states, dones = self.memory.sample(self.cfg.batch_size)
        states_t = torch.tensor(states, dtype=torch.float32, device=self.device)
        actions_t = torch.tensor(actions, dtype=torch.long, device=self.device).unsqueeze(1)
        rewards_t = torch.tensor(rewards, dtype=torch.float32, device=self.device).unsqueeze(1)
        next_states_t = torch.tensor(next_states, dtype=torch.float32, device=self.device)
        dones_t = torch.tensor(dones, dtype=torch.float32, device=self.device).unsqueeze(1)

        with torch.no_grad():
            next_actions = self.policy_net(next_states_t).argmax(1, keepdim=True)
            next_q_values = self.target_net(next_states_t).gather(1, next_actions)
            target_q = rewards_t + (self.gamma * next_q_values * (1 - dones_t))

        curr_q = self.policy_net(states_t).gather(1, actions_t)
        loss = nn.SmoothL1Loss()(curr_q, target_q)
        self.my_state.update(last_loss=float(loss.item()))

        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
        self.optimizer.step()

        for target_param, local_param in zip(
            self.target_net.parameters(), self.policy_net.parameters()
        ):
            target_param.data.copy_(
                self.tau * local_param.data + (1.0 - self.tau) * target_param.data
            )

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
        if self.steps_done % 20 == 0:
            self.writer.add_scalar("Training/Loss", float(loss.item()), int(self.steps_done))

    def compute(self, target_do, raw_do, raw_temp, raw_mlss, raw_ph) -> float:
        current_do = self.filter_do.update(_safe_float_opt(raw_do, default=None))
        temp = self.filter_temp.update(_safe_float_opt(raw_temp, default=None))
        safe_mlss = _safe_float(raw_mlss, default=3000.0)
        safe_ph = _safe_float(raw_ph, default=7.0)
        safe_target_do = _clamp(_safe_float(target_do, default=2.0), 0.0, 10.0)

        self.my_state.update(
            target_do=float(safe_target_do),
            do_filt=float(current_do),
            temp_filt=float(temp),
            memory_len=int(len(self.memory)),
        )

        with self._lock:
            current_state_vec = self.get_state_vector(
                safe_target_do, current_do, temp, safe_mlss, safe_ph
            )
            self.my_state.update(state_vector=current_state_vec)

            if (
                self.cfg.train_mode
                and self.last_state is not None
                and self.last_action_idx is not None
            ):
                abs_diff = abs(safe_target_do - current_do)
                reward = math.exp(-abs_diff * 2.0)
                if abs_diff < 0.1:
                    reward += 1.0
                elif abs_diff > 1.0:
                    reward -= 1.0
                if self.current_hz > 45.0:
                    reward -= 0.05
                self.my_state.update(last_reward=float(reward))

                self.memory.push(
                    self.last_state, self.last_action_idx, reward, current_state_vec, False
                )
                self.update_model()

            action_idx = self.select_action(current_state_vec)
            delta_hz = self.action_map[action_idx]
            proposed_hz = self.current_hz + delta_hz
            final_hz = SafetyLayer.apply_guard(safe_target_do, current_do, proposed_hz, self.cfg)

            self.last_state = current_state_vec
            self.last_action_idx = action_idx
            self.current_hz = float(final_hz)

            self.my_state.update(
                proposed_hz=float(proposed_hz),
                current_hz=float(final_hz),
                last_action_idx=int(action_idx),
                last_action_delta=float(delta_hz),
            )
            return float(self.current_hz)


# -----------------------------------------------------------------------------
# 4. MANAGER (The Orchestrator) - 🚀 다중 장비 스케일 아웃 엔진
# -----------------------------------------------------------------------------
class WorkerManager:
    def __init__(self) -> None:
        self._core_tasks: list[asyncio.Task] = []

        # 각 RTU 장비의 폴링(Polling) 스레드를 개별적으로 관리
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
        if rtu_id not in self.ctrls:
            self.ctrls[rtu_id] = ImmortalAgent(SITE, rtu_id)
        return self.ctrls[rtu_id]

    async def initialize(self) -> None:
        self._running = True

        self.compute_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="AI_Core")
        self.io_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="IO_Saver")

        if _is_windows and not STRICT_DURABILITY:
            logger.warning("Windows detected: STRICT_DURABILITY defaulted to 0 (warn-only).")

        loop = asyncio.get_running_loop()
        self._core_tasks.append(loop.create_task(run_db_writer(), name="DBWriter"))
        self._core_tasks.append(loop.create_task(self._control_loop(), name="ControlLoop"))
        self._core_tasks.append(
            loop.create_task(self._command_dispatcher_loop(), name="CommandDispatcher")
        )

        # 🚀 [패치 완료] 무거운 DB 엔진 대신 JSON 설정 파일(device_config.json)을 읽어옵니다.
        configs = load_device_configs()
        for config_dict in configs:
            await self.start_poller(config_dict)
            get_ai_state(config_dict["id"]).update(running=True, fatal=False, last_error=None)

        logger.info(f"✅ Immortal AI Manager Started (Loaded {len(configs)} devices from JSON).")

    # 🚀 [UI 연동 전용 API] 특정 기기를 새로 추가하고 통신 시작
    async def add_worker(self, rtu_id: int) -> None:
        config_dict = get_device_config(rtu_id)
        if config_dict:
            await self.start_poller(config_dict)
            get_ai_state(rtu_id).update(running=True, fatal=False, last_error=None)
            logger.info(
                f"🟢 [Device {rtu_id}] 파일에서 설정을 읽어 워커가 성공적으로 추가되었습니다."
            )
        else:
            logger.error(
                f"❌ [Device {rtu_id}] device_config.json 에서 해당 기기를 찾을 수 없어 워커를 추가할 수 없습니다."
            )

    # 🚀 [UI 연동 전용 API] 특정 기기의 설정을 변경하고 재시작
    async def update_worker(self, rtu_id: int) -> None:
        logger.info(f"🔄 [Device {rtu_id}] 통신 워커 재시작을 시도합니다.")
        await self.add_worker(rtu_id)  # start_poller가 내부적으로 기존 워커를 끄고 켜줍니다.

    async def start_poller(self, config: dict) -> None:
        # 🚀 인자가 DB 객체(ConnectionConfig)에서 Dictionary(JSON) 형태로 변경되었습니다!
        rtu_id = config["id"]
        protocol_str = config.get("protocol", BackendType.MODBUS.value)
        host = config.get("host", "127.0.0.1")

        await self.stop_poller(rtu_id)  # 이미 돌고 있다면 안전하게 끄고 시작

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
            logger.info(f"🏭 Deployed Poller Worker for Device [{rtu_id}] ({protocol_str})")

    async def stop_poller(self, rtu_id: int) -> None:
        if rtu_id in self._poller_tasks:
            task = self._poller_tasks.pop(rtu_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info(f"🛑 Stopped Poller Worker for Device [{rtu_id}]")

    # 🚀 통신 설정 변경 (JSON 지원)
    async def apply_comm_settings(self, rtu_id: int, port: str, baudrate: int) -> bool:
        logger.info(f"🔄 UI 요청: [Device {rtu_id}] 통신 설정 변경 ({port} @ {baudrate}bps)")
        configs = load_device_configs()
        found = False
        for c in configs:
            if c["id"] == rtu_id:
                c["host"] = port
                c["port"] = baudrate
                c["protocol"] = BackendType.MODBUS.value
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

    # 🚀 통신 강제 해제 (JSON 지원)
    async def disconnect_comm(self, rtu_id: int) -> None:
        logger.info(f"🛑 UI 요청: [Device {rtu_id}] 통신 강제 해제")
        await self.stop_poller(rtu_id)

        configs = load_device_configs()
        for c in configs:
            if c["id"] == rtu_id:
                c["host"] = ""  # 호스트를 날려버려서 접속을 끊음
                break
        save_device_configs(configs)

    async def stop_workers(self) -> None:
        self._running = False
        for rtu_id in self._poller_tasks.keys():
            get_ai_state(rtu_id).update(running=False)

        for rtu_id in list(self._poller_tasks.keys()):
            await self.stop_poller(rtu_id)

        for task in self._core_tasks:
            task.cancel()
        if self._core_tasks:
            await asyncio.gather(*self._core_tasks, return_exceptions=True)
        self._core_tasks = []

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
        logger.info("👋 System Shutdown Complete.")

    def _fatal_persist(self, exc: BaseException) -> None:
        with self._fatal_lock:
            if self._fatal_triggered:
                return
            self._fatal_triggered = True
        for rtu_id in list(self._poller_tasks.keys()) + list(self.ctrls.keys()):
            get_ai_state(rtu_id).update(fatal=True, running=False, last_error=str(exc))
        logger.critical("FATAL: Checkpoint persistence failed.", exc_info=exc)
        self._running = False
        for t in self._core_tasks + list(self._poller_tasks.values()):
            t.cancel()

        def _exit_worker():
            try:
                try:
                    logging.shutdown()
                except Exception:
                    pass
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

    # 🚀 [핵심 패치] 하드코딩 탈피! JSON에 설정된 주소를 동적으로 읽어옵니다.
    async def _command_dispatcher_loop(self) -> None:
        logger.info("📡 Modbus Command Dispatcher Started (Fully Dynamic Mode).")
        while self._running:
            try:
                rtu_id, cmd, val = await command_q.get()

                config_dict = get_device_config(rtu_id)
                tags = config_dict.get("tags", {})

                # 1. 펌프(set_hz)는 C# 장비 통신 규격상 무조건 * 10.0 이 필요하므로 예외 처리
                if cmd == "set_hz":
                    target_val = int(val * 10.0)
                    addr = tags.get("set_hz", {}).get("mb_addr", 29)
                    await write_hr_single(rtu_id, addr, target_val)

                # 2. JSON에 등록된 일반 태그 (예: valve_pos 및 미래에 추가될 모든 장비)
                elif cmd in tags:
                    target_val = int(val)
                    addr = tags[cmd].get("mb_addr")
                    if addr is not None:
                        await write_hr_single(rtu_id, addr, target_val)

                # 3. JSON에 등록되지 않은 순수 주소 직접 타격 (캐시 이슈나 임시 테스트용 완벽 방어)
                elif str(cmd).startswith("raw_"):
                    target_val = int(val)
                    addr = int(str(cmd).split("_")[1])
                    await write_hr_single(rtu_id, addr, target_val)

                command_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Command Dispatch Error: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _control_loop(self) -> None:
        loop = asyncio.get_running_loop()
        save_tick = 0

        while self._running:
            start_time = time.monotonic()
            try:
                for rtu_id, state in sys_states.items():
                    # HMI 내부 '자동 제어 모드'가 켜져 있을 때 작동
                    if getattr(state, "auto_mode", False):
                        agent = self._get_agent(rtu_id)

                        target_do = getattr(state, "target_do", 2.0)
                        curr_do = getattr(state, "last_do", 0.0)
                        temp = getattr(state, "last_temp", 0.0)
                        mlss = getattr(state, "last_mlss", 0.0)
                        ph = getattr(state, "last_ph", 0.0)

                        # AI가 최적의 펌프 주파수(Hz)를 계산
                        target_hz = await loop.run_in_executor(
                            self.compute_executor,
                            agent.compute,
                            target_do,
                            curr_do,
                            temp,
                            mlss,
                            ph,
                        )

                        # 🚀 [핵심 패치 1] 현장 장비(시뮬레이터)의 밸브 스위치가 'Auto'일 때만 HMI가 덮어씁니다!
                        if getattr(state, "valve_auto", False):
                            await command_q.put((rtu_id, "valve_pos", float(SITE.base_valve_pos)))

                        # 🚀 [핵심 패치 2] 현장 장비(시뮬레이터)의 펌프 스위치가 'Auto'일 때만 HMI가 덮어씁니다!
                        if getattr(state, "pump_auto", False):
                            await command_q.put((rtu_id, "set_hz", float(target_hz)))

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
                logger.error("Loop Error: %s", e, exc_info=True)
                await asyncio.sleep(1.0)

            elapsed = time.monotonic() - start_time
            await asyncio.sleep(max(0.1, SITE.dt - elapsed))


manager = WorkerManager()
worker_manager = manager
