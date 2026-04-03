# app/workers/ai/agent.py
import math
import time
import random
import shutil
import threading
from collections import deque
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.tensorboard import SummaryWriter

# PyTorch가 시스템 CPU를 독점하지 않도록 적절히 제한 (정석 세팅)
torch.set_num_threads(2)

from app.workers.ai.config import SystemConfig
from app.workers.ai.utils import (
    EMAFilter,
    SafetyLayer,
    _clamp,
    _gc_files,
    _durable_backup,
    _save_torch_atomic,
    _fsync_dir,
    _safe_float_opt,
    _safe_float,
)
from app.workers.ai.model import DuelingQNetwork, ReplayBuffer
from app.workers.ai_state import get_ai_state


class ImmortalAgent:
    def __init__(self, config: SystemConfig, rtu_id: int):
        self.cfg = config
        self.rtu_id = rtu_id

        self.model_dir = Path(".data/ai_models")
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.brain_path = self.model_dir / f"immortal_brain_v2_rtu_{self.rtu_id}.pth"
        self.memory_path = self.model_dir / f"immortal_memory_v2_rtu_{self.rtu_id}.pkl.xz"

        self.state_dim = 9
        self.action_map = [-2.0, -1.0, -0.5, -0.1, 0.0, 0.1, 0.5, 1.0, 2.0]
        self.action_dim = len(self.action_map)

        self.device = torch.device("cpu")
        self._lock = threading.RLock()
        self.my_state = get_ai_state(self.rtu_id)

        # 신경망 초기화
        self.policy_net = DuelingQNetwork(self.state_dim, self.action_dim).to(self.device)
        self.target_net = DuelingQNetwork(self.state_dim, self.action_dim).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.AdamW(self.policy_net.parameters(), lr=self.cfg.learning_rate)
        self.criterion = nn.SmoothL1Loss()

        self.memory = ReplayBuffer(capacity=self.cfg.memory_capacity, state_dim=self.state_dim)
        self.memory.load_memory_compressed(self.memory_path)

        # 하이퍼파라미터
        self.gamma = 0.98
        self.tau = 0.005
        self.epsilon = 1.0
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.9995

        # 상태 제어 변수
        self.integral_error = 0.0
        self.history = deque(maxlen=10)
        self.last_state = None
        self.last_action_idx = None
        self.current_hz = 40.0
        self.steps_done = 0

        self.filter_do = EMAFilter(alpha=0.4)
        self.filter_temp = EMAFilter(alpha=0.1)

        run_dir = self.model_dir / "runs" / f"rtu_{self.rtu_id}"
        self.writer = SummaryWriter(log_dir=str(run_dir))

        self._load_brain()

        # 🚀 [정석 아키텍처] 백그라운드 학습 스레드 분리 (Learner)
        # 제어 루프를 방해하지 않고 뒤에서 독립적으로 모델을 학습합니다.
        self._is_running = True
        self._train_thread = threading.Thread(
            target=self._learner_loop, daemon=True, name=f"AI_Learner_RTU_{self.rtu_id}"
        )
        self._train_thread.start()

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
            if isinstance(checkpoint, dict) and "model_state" in checkpoint:
                state_dict = checkpoint["model_state"]
                self.steps_done = int(checkpoint.get("steps_done", 0))
                self.epsilon = float(checkpoint.get("epsilon", 1.0))
                opt_state = checkpoint.get("optimizer_state", None)
            else:
                state_dict = checkpoint
                self.steps_done = int(len(self.memory))
                self.epsilon = float(self.epsilon_min)
                opt_state = None

            current_dict = self.policy_net.state_dict()
            if "feature_layer.0.weight" in state_dict and "feature_layer.0.weight" in current_dict:
                if (
                    state_dict["feature_layer.0.weight"].shape
                    != current_dict["feature_layer.0.weight"].shape
                ):
                    old_dim_path = self.brain_path.with_name(self.brain_path.name + ".old_dim")
                    shutil.move(self.brain_path, old_dim_path)
                    return

            self.policy_net.load_state_dict(state_dict)
            self.target_net.load_state_dict(state_dict)
            if opt_state:
                self.optimizer.load_state_dict(opt_state)
        except Exception:
            pass

    def save_checkpoint_task(self) -> None:
        self.my_state.update(save_inflight=True)
        try:
            _gc_files(self.model_dir, f"{self.brain_path.name}.tmp.*", older_than_sec=0)
            _gc_files(self.model_dir, f"{self.memory_path.name}.tmp.*", older_than_sec=0)

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

            bak_name = self.brain_path.name + ".bak"
            if self.brain_path.exists():
                _durable_backup(self.brain_path, self.brain_path.with_name(bak_name))
            _save_torch_atomic(self.brain_path, checkpoint_data)
            if mem_snapshot:
                self.memory.save_memory_compressed(self.memory_path, snapshot=mem_snapshot)
            self.my_state.update(last_save_ts=time.time(), last_save_ok=True)
        except Exception as e:
            self.my_state.update(last_save_ok=False, last_error=str(e))
            raise
        finally:
            self.my_state.update(save_inflight=False)

    def get_state_vector(
        self, target_do: float, current_do: float, temp: float, mlss: float, ph: float
    ) -> list[float]:
        error = target_do - current_do
        self.history.append(current_do)
        slope = self.history[-1] - self.history[0] if len(self.history) >= 3 else 0.0
        delta_do = self.history[-1] - self.history[-2] if len(self.history) >= 2 else 0.0
        self.integral_error = _clamp(self.integral_error + error, -10.0, 10.0)

        raw_state = [
            error,
            slope * 5.0,
            delta_do * 10.0,
            self.integral_error / 10.0,
            (self.current_hz - 40.0) / 20.0,
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

        if self.cfg.train_mode and random.random() < current_epsilon:
            return random.randint(0, self.action_dim - 1)

        with torch.no_grad():
            state_tensor = torch.tensor(
                state_vec, dtype=torch.float32, device=self.device
            ).unsqueeze(0)
            q_vals = self.policy_net(state_tensor)
            q_vals_list = [float(x) for x in q_vals.squeeze(0).cpu().tolist()]
            action = int(q_vals.argmax(dim=1).item())

        self.my_state.update(q_values=q_vals_list)
        return action

    # 🚀 [정석 아키텍처] 백그라운드 전용 학습 루프
    def _learner_loop(self) -> None:
        """독립된 스레드에서 일정한 간격으로 모델을 학습하여 메모리 누수와 CPU 폭주 방지"""
        while self._is_running:
            if self.cfg.train_mode and len(self.memory) >= self.cfg.batch_size:
                try:
                    self._update_model()
                except Exception as e:
                    pass  # 로그 추가 가능

            # 실시간 제어 스레드와 완전히 분리되어, 1초에 한 번만 여유롭게 학습 진행
            # 이 유휴 시간 동안 파이썬의 가비지 컬렉터(GC)가 사용 끝난 텐서를 완벽하게 정리함
            time.sleep(1.0)

    def _update_model(self) -> None:
        """순수 학습 연산 로직 (Learner 스레드에서만 호출됨)"""
        # 스레드 안전성을 위해 샘플링 및 학습 구간 전체에 락 적용
        with self._lock:
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
            loss = self.criterion(curr_q, target_q)
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

            if self.steps_done % 10 == 0:
                self.writer.add_scalar("Training/Loss", float(loss.item()), int(self.steps_done))
                self.writer.flush()

    def compute(
        self, target_do: float, raw_do: float, raw_temp: float, raw_mlss: float, raw_ph: float
    ) -> float:
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

                allowed_hz = 40.0 + (safe_target_do * 4.0)
                energy_penalty = max(0.0, (self.current_hz - allowed_hz) * 0.01)
                reward -= energy_penalty
                if self.current_hz > allowed_hz + 10.0:
                    reward -= 0.5

                self.my_state.update(last_reward=float(reward))

                # 🚀 [정석 아키텍처 핵심] 여기 있던 self.update_model() 호출 제거!
                # Actor는 그저 큐(ReplayBuffer)에 데이터를 쌓고 빠르게 제어 루프로 돌아갑니다.
                self.memory.push(
                    self.last_state, self.last_action_idx, reward, current_state_vec, False
                )

            action_idx = self.select_action(current_state_vec)
            delta_hz = self.action_map[action_idx]
            proposed_hz = self.current_hz + delta_hz

            self.last_state = current_state_vec
            self.last_action_idx = action_idx
            self.current_hz = float(proposed_hz)

            self.my_state.update(
                proposed_hz=float(proposed_hz),
                current_hz=float(self.current_hz),
                last_action_idx=int(action_idx),
                last_action_delta=float(delta_hz),
            )

            return self.current_hz

    def close(self):
        """프로그램 종료 시 스레드를 안전하게 닫습니다."""
        self._is_running = False
        if hasattr(self, "_train_thread"):
            self._train_thread.join(timeout=2.0)
        self.writer.close()
