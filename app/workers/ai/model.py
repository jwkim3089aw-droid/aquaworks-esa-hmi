# app/workers/ai/model.py
import torch
import torch.nn as nn
import random
import pickle
import lzma
import os
import logging
from collections import deque
from pathlib import Path
from typing import List, Tuple, Optional, Any

from app.workers.ai.utils import _save_lzma_pickle_atomic, _unique_corrupt

logger = logging.getLogger("IMMORTAL_AI_MODEL")


class DuelingQNetwork(nn.Module):
    """
    Dueling Deep Q-Network 모델
    - 현장 센서 데이터의 스케일 차이를 완화하기 위해 LayerNorm 적용
    - Value(상태 가치)와 Advantage(행동 우위)를 분리하여 평가
    """

    def __init__(self, state_dim: int, action_dim: int):
        super().__init__()

        # 1. 공통 특징 추출 계층 (Feature Extractor)
        self.feature_layer = nn.Sequential(
            nn.Linear(state_dim, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
        )

        # 2. Value Stream (현재 상태 s가 얼마나 좋은가?)
        self.value_stream = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 1))

        # 3. Advantage Stream (상태 s에서 특정 행동 a를 하는 것이 얼마나 더 좋은가?)
        self.advantage_stream = nn.Sequential(
            nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, action_dim)
        )

        # 가중치 초기화 적용 (He Initialization)
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(m: nn.Module) -> None:
        """ReLU 활성화 함수에 최적화된 Kaiming(He) Normal 초기화"""
        if isinstance(m, nn.Linear):
            nn.init.kaiming_normal_(m.weight, nonlinearity="relu")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Q(s, a) = V(s) + (A(s, a) - mean(A(s, a)))
        평균을 빼줌으로써 식별성(Identifiability) 문제를 해결하고 학습을 안정화
        """
        features = self.feature_layer(x)
        values = self.value_stream(features)
        advantages = self.advantage_stream(features)

        # 차원 유지(keepdim=True)를 통해 브로드캐스팅 연산 수행
        return values + (advantages - advantages.mean(dim=1, keepdim=True))


class ReplayBuffer:
    """
    경험 재생 버퍼 (Experience Replay Buffer)
    - 손상된 센서 데이터 유입 방지를 위한 강력한 검증(Sanitize) 로직 포함
    - LZMA 압축 및 원자적(Atomic) 파일 저장을 통한 영속성(Durability) 보장
    """

    def __init__(self, capacity: int = 50000, state_dim: int = 9):
        self.buffer = deque(maxlen=capacity)
        self.state_dim = int(state_dim)

    @staticmethod
    def _to_float_list(x: Any) -> List[float]:
        """입력 데이터를 안전하게 1차원 float 리스트로 변환"""
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

    def _sanitize_transition(
        self, item: Tuple
    ) -> Optional[Tuple[List[float], int, float, List[float], float]]:
        """메모리에 적재할 트랜지션(State, Action, Reward, Next_State, Done)의 무결성 검증"""
        try:
            s, a, r, ns, d = item
            s = self._to_float_list(s)
            ns = self._to_float_list(ns)

            # 차원이 맞지 않는 깨진 데이터는 필터링
            if len(s) != self.state_dim or len(ns) != self.state_dim:
                return None

            return (s, int(a), float(r), ns, float(bool(d)))
        except Exception:
            return None

    def push(self, state: Any, action: int, reward: float, next_state: Any, done: bool) -> None:
        """새로운 경험을 버퍼에 추가"""
        s = self._to_float_list(state)
        ns = self._to_float_list(next_state)

        if len(s) != self.state_dim or len(ns) != self.state_dim:
            return

        self.buffer.append((s, int(action), float(reward), ns, float(bool(done))))

    def sample(
        self, batch_size: int
    ) -> Tuple[List[List[float]], List[int], List[float], List[List[float]], List[float]]:
        """학습을 위한 미니 배치 무작위 추출"""
        batch = random.sample(self.buffer, batch_size)

        states = [b[0] for b in batch]
        actions = [b[1] for b in batch]
        rewards = [b[2] for b in batch]
        next_states = [b[3] for b in batch]
        dones = [b[4] for b in batch]

        return states, actions, rewards, next_states, dones

    def __len__(self) -> int:
        return len(self.buffer)

    def save_memory_compressed(self, path: Path, snapshot: Optional[List] = None) -> None:
        """메모리 버퍼 압축 저장 (정전 대비 원자적 쓰기)"""
        data_to_save = snapshot if snapshot is not None else list(self.buffer)
        _save_lzma_pickle_atomic(path, data_to_save)

    def load_memory_compressed(self, path: Path) -> None:
        """압축된 메모리 파일 로드 및 손상 복구"""
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
            # 파일이 심각하게 손상된 경우 격리 처리 후 새로 시작
            try:
                corrupt = _unique_corrupt(path)
                os.replace(path, corrupt)
                logger.warning(f"🚨 Memory file corrupted. Moved to {corrupt.name}")
            except Exception:
                pass
