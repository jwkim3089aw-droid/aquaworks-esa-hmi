# app/workers/ai_state.py
from __future__ import annotations
from dataclasses import dataclass, field
from threading import RLock
from typing import Optional, Dict, Any, List, Tuple
import time
import logging

logger = logging.getLogger("AI_STATE")


@dataclass
class AIState:
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _unknown_keys: set[str] = field(default_factory=set, init=False, repr=False)

    # UI 렌더링 최적화용 시퀀스
    seq: int = 0
    q_seq: int = 0

    # 1. 상태 및 헬스체크
    running: bool = False
    fatal: bool = False
    last_error: Optional[str] = None
    last_heartbeat_ts: float = 0.0

    # 2. 학습 지표
    train_mode: bool = True
    epsilon: float = 0.0
    steps_done: int = 0
    memory_len: int = 0
    last_loss: Optional[float] = None
    last_reward: Optional[float] = None

    # 3. 의사결정 데이터
    current_hz: Optional[float] = None
    proposed_hz: Optional[float] = None
    last_action_idx: Optional[int] = None
    last_action_delta: Optional[float] = None

    action_map: List[float] = field(default_factory=list)
    q_values: List[float] = field(default_factory=list)
    state_vector: List[float] = field(default_factory=list)

    # 4. 관측값
    target_do: Optional[float] = None
    do_filt: Optional[float] = None
    temp_filt: Optional[float] = None

    # 5. 저장 상태
    save_inflight: bool = False
    last_save_ts: Optional[float] = None
    last_save_ok: Optional[bool] = None

    def update(self, **kwargs: Any) -> None:
        """
        데이터 변경 시 seq 증가.
        데이터 없이 호출 시 심박수만 갱신.
        리스트 타입은 안전하게 복사하여 저장.
        """
        now = time.monotonic()
        with self._lock:
            self.last_heartbeat_ts = now

            if not kwargs:
                return

            has_change = False
            for k, v in kwargs.items():
                if hasattr(self, k):
                    # [SAFETY] 리스트 참조 끊기 (외부 수정 방지)
                    if k in ("action_map", "q_values", "state_vector") and v is not None:
                        v = list(v)

                    setattr(self, k, v)
                    has_change = True

                    if k in ("q_values", "action_map"):
                        self.q_seq += 1
                else:
                    if k not in self._unknown_keys:
                        logger.warning("AIState update ignored invalid key: %s", k)
                        self._unknown_keys.add(k)

            if has_change:
                self.seq += 1

    def peek_meta(self) -> Tuple[int, int, float, bool, bool, Optional[str], bool, bool]:
        """
        UI가 매 틱마다 호출하여 상태를 체크하는 용도.
        Return: (seq, q_seq, last_heartbeat_ts, running, fatal, last_error, save_inflight, train_mode)
        """
        with self._lock:
            return (
                self.seq,
                self.q_seq,
                self.last_heartbeat_ts,
                self.running,
                self.fatal,
                self.last_error,
                self.save_inflight,
                self.train_mode,
            )

    def snapshot_if_changed(
        self, last_seq: int, max_state_vector: int = 64
    ) -> Tuple[int, int, Optional[Dict[str, Any]]]:
        """
        seq가 다를 때만 스냅샷 생성.
        Return: (current_seq, current_q_seq, snapshot_dict)
        """
        with self._lock:
            if self.seq == last_seq:
                return self.seq, self.q_seq, None

            # 수동 딕셔너리 생성 (가장 빠름)
            snap: Dict[str, Any] = {
                "seq": self.seq,
                "q_seq": self.q_seq,
                "running": self.running,
                "fatal": self.fatal,
                "last_error": self.last_error,
                "last_heartbeat_ts": self.last_heartbeat_ts,
                "train_mode": self.train_mode,
                "epsilon": self.epsilon,
                "steps_done": self.steps_done,
                "memory_len": self.memory_len,
                "last_loss": self.last_loss,
                "last_reward": self.last_reward,
                "current_hz": self.current_hz,
                "proposed_hz": self.proposed_hz,
                "last_action_idx": self.last_action_idx,
                "last_action_delta": self.last_action_delta,
                "action_map": list(self.action_map),
                "q_values": list(self.q_values),
                "state_vector": self.state_vector[:max_state_vector],
                "target_do": self.target_do,
                "do_filt": self.do_filt,
                "temp_filt": self.temp_filt,
                "save_inflight": self.save_inflight,
                "last_save_ts": self.last_save_ts,
                "last_save_ok": self.last_save_ok,
            }
            return self.seq, self.q_seq, snap


_ai_states: Dict[int, AIState] = {}


def get_ai_state(rtu_id: int) -> AIState:
    """
    특정 RTU 장비 전용 AI 상태 객체를 반환하거나 새로 생성합니다.
    """
    if rtu_id not in _ai_states:
        _ai_states[rtu_id] = AIState()
    return _ai_states[rtu_id]


# 기존 단일 장비 API가 당장 터지지 않도록 1번 기기를 기본값으로 할당 (하위 호환성)
ai_state = get_ai_state(1)
