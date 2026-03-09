# simulator/observability/snapshot.py
from __future__ import annotations

import base64
import hashlib
import json
import pickle
import time
from typing import Any, Optional, TypeAlias

from pydantic import BaseModel, Field, ConfigDict

from simulator.config import SimulationConfig
from simulator.state import ModelState


SNAPSHOT_VERSION = 1

RngState: TypeAlias = tuple[Any, ...]  # random.Random.getstate() returns a tuple


def config_fingerprint(cfg: SimulationConfig) -> str:
    payload = cfg.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def encode_rng_state(rng_state: RngState) -> str:
    b = pickle.dumps(rng_state, protocol=pickle.HIGHEST_PROTOCOL)
    return base64.b64encode(b).decode("ascii")


def decode_rng_state(s: str) -> RngState:
    b = base64.b64decode(s.encode("ascii"))
    state = pickle.loads(b)
    # runtime safety
    if not isinstance(state, tuple):
        raise TypeError("Decoded RNG state is not a tuple.")
    return state  # type: ignore[return-value]


class SnapshotEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    version: int = Field(default=SNAPSHOT_VERSION, ge=1)
    created_at: float = Field(default_factory=time.time)

    config_hash: str
    config: SimulationConfig
    state: ModelState

    rng_state_b64: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def build(
        cls,
        cfg: SimulationConfig,
        state: ModelState,
        rng_state: Optional[RngState],
        meta: dict[str, Any],
    ) -> "SnapshotEnvelope":
        return cls(
            version=SNAPSHOT_VERSION,
            config_hash=config_fingerprint(cfg),
            config=cfg,
            state=state,
            rng_state_b64=encode_rng_state(rng_state) if rng_state is not None else None,
            meta=meta,
        )
