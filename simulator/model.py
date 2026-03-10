# simulator/model.py
from __future__ import annotations

import logging
import math
import random
import time
from typing import Any, Dict, Optional

from simulator.config import SimulationConfig
from simulator.state import ModelState, ControlInput
from simulator.numerics.integrator import substep_integrate
from simulator.components.pump import PumpModel
from simulator.components.ejector import EjectorModel
from simulator.components.aeration import AerationModel
from simulator.components.thermal import ThermalModel
from simulator.observability.snapshot import SnapshotEnvelope, decode_rng_state, RngState

logger = logging.getLogger(__name__)


class ESAProcessModel:
    def __init__(self, config: Optional[SimulationConfig] = None):
        self.cfg: SimulationConfig = (
            config if config is not None else SimulationConfig.model_validate({})
        )
        self.state: ModelState = ModelState.model_validate({})

        self.rng = random.Random(self.cfg.rng_seed)

        self.pump = PumpModel(self.cfg.pump, self.cfg.system)
        self.ejector = EjectorModel(self.cfg.ejector)
        self.aeration = AerationModel(self.cfg.aeration, self.cfg.system, self.rng)
        self.thermal = ThermalModel(self.cfg.system)

        self._last_mono = time.monotonic()

        logger.info("ESAProcessModel initialized.")

    # ---------------------------
    # Public API
    # ---------------------------
    def set_controls(self, pump_hz: float, valve_open_pct: float) -> None:
        controls = ControlInput.model_validate(
            {"pump_hz": pump_hz, "valve_open_pct": valve_open_pct}
        )
        self.state.controls = controls

    def update(self) -> None:
        now_mono = time.monotonic()
        dt_real = now_mono - self._last_mono
        if dt_real <= 0:
            return

        if dt_real > self.cfg.max_real_dt:
            dt_real = self.cfg.max_real_dt

        self._last_mono = now_mono

        # 시뮬레이션 속도 배율 적용
        dt_sim = dt_real * self.cfg.time_scale

        # 1. 물리/화학적 공정 상태 업데이트: dt_sim 기준
        substep_integrate(dt_sim, self.cfg.max_dt, self._substep)

        # 2. 센서/표시값 업데이트: dt_real 기준
        self._update_sensors(dt_real)

        self.state.wall_timestamp = time.time()

    def reset(self) -> None:
        logger.warning("Reset triggered.")
        self.state = ModelState.model_validate({})
        self.rng = random.Random(self.cfg.rng_seed)
        self.aeration = AerationModel(self.cfg.aeration, self.cfg.system, self.rng)
        self._last_mono = time.monotonic()

    def get_snapshot(self) -> Dict[str, Any]:
        rng_state: RngState = self.rng.getstate()
        env = SnapshotEnvelope.build(
            cfg=self.cfg,
            state=self.state,
            rng_state=rng_state,
            meta={"note": "ESAProcessModel snapshot"},
        )
        return env.model_dump(mode="json")

    def load_snapshot(self, data: Dict[str, Any]) -> None:
        env = SnapshotEnvelope.model_validate(data)

        self.cfg = env.config
        self.pump = PumpModel(self.cfg.pump, self.cfg.system)
        self.ejector = EjectorModel(self.cfg.ejector)
        self.thermal = ThermalModel(self.cfg.system)
        self.state = env.state
        self.rng = random.Random(self.cfg.rng_seed)
        if env.rng_state_b64:
            self.rng.setstate(decode_rng_state(env.rng_state_b64))

        self.aeration = AerationModel(self.cfg.aeration, self.cfg.system, self.rng)
        self._last_mono = time.monotonic()
        self.state.wall_timestamp = time.time()
        logger.info("Snapshot loaded.")

    # ---------------------------
    # Internal stepping
    # ---------------------------
    def _substep(self, dt: float) -> None:
        s = self.state
        c = s.controls

        s.sim_hour = (s.sim_hour + dt / 3600.0) % 24.0

        self.pump.step(dt, s, c)
        self.ejector.step(dt, s, c)

        # 🚀 [물리법칙] 밸브가 잠겨있으면 에어 차단
        if c.valve_open_pct <= 0.1:
            s.air_flow_lpm = 0.0
        else:
            s.air_flow_lpm = s.air_flow_lpm * (c.valve_open_pct / 100.0)

        self.aeration.step(dt, s)
        self.thermal.step(dt, s)
        self._step_mlss_true_process(dt)
        self._step_ph_true_process(dt)

        # 🚀 [에너지 누적 정상 유지] 매 초(dt)마다 전력(kW)을 에너지(kWh)로 누적 계산
        s.energy_kwh += s.power_kw * (dt / 3600.0)

    def _step_mlss_true_process(self, dt: float) -> None:
        s = self.state
        if dt <= 0:
            return

        base_target = 3000.0
        srt_days = 15.0
        theta = 1.04
        ks_do = 0.5
        q_ref = 50.0

        do = max(0.0, s.do_mgL)
        f_do = do / (ks_do + do) if (ks_do + do) > 0 else 0.0
        f_t = max(0.8, min(1.3, theta ** (s.temp_c - 20.0)))
        q = max(0.0, s.flow_m3h)
        f_load = 0.6 if q <= 1e-9 else min(1.0, q / max(1e-6, q_ref))

        target = base_target * (0.95 + 0.10 * f_do) * (0.95 + 0.10 * f_load) * f_t
        tau_sec = max(1.0, srt_days) * 86400.0

        diff = target - s.mlss_true_mgL
        s.mlss_true_mgL += diff * (dt / tau_sec)

        proc_sigma = 0.05
        noise = proc_sigma * math.sqrt(dt) * self.rng.gauss(0.0, 1.0)
        s.mlss_true_mgL = max(500.0, min(8000.0, s.mlss_true_mgL + noise))

    def _step_ph_true_process(self, dt: float) -> None:
        s = self.state
        if dt <= 0:
            return

        base_ph = 7.2
        tau_sec = 3600.0 * 24.0

        do = max(0.0, s.do_mgL)
        nitrification_drop = 0.3 * (do / (1.0 + do))
        temp_effect = (s.temp_c - 20.0) * 0.015

        q = max(0.0, s.flow_m3h)
        load_factor = min(1.0, q / max(1e-6, 50.0))
        buffer_recovery = 0.15 * load_factor

        target_ph = max(6.2, min(8.3, base_ph - nitrification_drop - temp_effect + buffer_recovery))
        diff = target_ph - s.ph
        s.ph += diff * (dt / tau_sec)

        noise = 0.0001 * math.sqrt(dt) * self.rng.gauss(0.0, 1.0)
        s.ph = max(5.5, min(9.0, s.ph + noise))

    def _update_sensors(self, dt: float) -> None:
        s = self.state
        if dt <= 0:
            return
        noise_std = 20.0
        tau_filter = 30.0
        raw_meas = s.mlss_true_mgL + self.rng.gauss(0.0, noise_std)
        alpha = 1.0 - math.exp(-dt / max(0.5, tau_filter))
        s.mlss += alpha * (raw_meas - s.mlss)

    # ------------------------------------------------------------------
    # Legacy compatibility layer
    # ------------------------------------------------------------------
    @property
    def pump_hz(self) -> float:
        return self.state.controls.pump_hz

    @pump_hz.setter
    def pump_hz(self, v: float) -> None:
        self.set_controls(pump_hz=v, valve_open_pct=self.state.controls.valve_open_pct)

    @property
    def valve_open(self) -> float:
        return self.state.controls.valve_open_pct

    @valve_open.setter
    def valve_open(self, v: float) -> None:
        self.set_controls(pump_hz=self.state.controls.pump_hz, valve_open_pct=v)

    @property
    def power(self) -> float:
        return self.state.power_kw

    @property
    def energy(self) -> float:
        return self.state.energy_kwh

    @property
    def do(self) -> float:
        return self.state.do_mgL

    @property
    def temp(self) -> float:
        return self.state.temp_c

    @property
    def air_flow(self) -> float:
        # 🚀 [오류 완벽 제거] 쓸데없이 스케일링을 줄였던 * 0.06 을 완전히 삭제했습니다!
        # 이제 다시 수백 단위(300~400)의 시원한 데이터가 HMI로 뿜어져 나갑니다.
        return self.state.air_flow_lpm

    @property
    def snapshot(self) -> Dict[str, Any]:
        return self.get_snapshot()

    @property
    def mlss(self) -> float:
        return self.state.mlss

    @property
    def ph(self) -> float:
        return self.state.ph
