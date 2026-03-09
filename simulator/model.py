# simiulator/model.py
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
        # Pylance-friendly default construction
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

        # adopt snapshot config
        self.cfg = env.config

        # rebuild components
        self.pump = PumpModel(self.cfg.pump, self.cfg.system)
        self.ejector = EjectorModel(self.cfg.ejector)
        self.thermal = ThermalModel(self.cfg.system)

        # restore state
        self.state = env.state

        # restore RNG
        self.rng = random.Random(self.cfg.rng_seed)
        if env.rng_state_b64:
            self.rng.setstate(decode_rng_state(env.rng_state_b64))

        self.aeration = AerationModel(self.cfg.aeration, self.cfg.system, self.rng)

        # sync timing
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
        self.aeration.step(dt, s)
        self.thermal.step(dt, s)

        # 공정의 "True" 상태 계산 (느린 변화)
        self._step_mlss_true_process(dt)
        self._step_ph_true_process(dt)  # 🚀 [패치] 정교한 pH 계산 로직 추가

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

        f_t = theta ** (s.temp_c - 20.0)
        f_t = max(0.8, min(1.3, f_t))

        q = max(0.0, s.flow_m3h)
        if q <= 1e-9:
            f_load = 0.6
        else:
            f_load = min(1.0, q / max(1e-6, q_ref))

        target = base_target * (0.95 + 0.10 * f_do) * (0.95 + 0.10 * f_load) * f_t
        tau_sec = max(1.0, srt_days) * 86400.0

        diff = target - s.mlss_true_mgL
        s.mlss_true_mgL += diff * (dt / tau_sec)

        proc_sigma = 0.05
        noise = proc_sigma * math.sqrt(dt) * self.rng.gauss(0.0, 1.0)

        s.mlss_true_mgL = max(500.0, min(8000.0, s.mlss_true_mgL + noise))

    def _step_ph_true_process(self, dt: float) -> None:
        """
        🚀 [생화학/빅데이터 기반 pH 동적 모델]
        폭기조 내의 질산화(Nitrification) 및 온도, 유량에 의한 알칼리도 변화와 완충(Buffering) 작용을 모사합니다.
        """
        s = self.state
        if dt <= 0:
            return

        # --- Parameters (화학적 특성) ---
        base_ph = 7.2  # 무부하 상태의 기준 pH
        tau_sec = 3600.0 * 2.0  # 2시간 시상수 (수조의 거대한 물량으로 인해 pH는 매우 천천히 변함)

        # 1. DO에 따른 질산화 영향 (H+ 이온 방출 -> pH 감소)
        # DO 농도가 높을수록 호기성 미생물의 대사가 활발해져 pH를 떨어뜨림
        do = max(0.0, s.do_mgL)
        nitrification_drop = 0.3 * (do / (1.0 + do))

        # 2. 온도에 따른 반응 속도 영향 (온도가 높을수록 대사율 증가)
        temp_effect = (s.temp_c - 20.0) * 0.015

        # 3. 유입수 부하에 따른 알칼리도 공급 (버퍼링)
        q = max(0.0, s.flow_m3h)
        q_ref = 50.0
        load_factor = min(1.0, q / max(1e-6, q_ref))
        buffer_recovery = 0.15 * load_factor

        # --- Target Calculation (동적 목표 pH) ---
        target_ph = base_ph - nitrification_drop - temp_effect + buffer_recovery

        # 극한 상황 방지 (어떤 상황에서도 물리적 한계를 벗어나지 않도록 강제 클램핑)
        target_ph = max(6.2, min(8.3, target_ph))

        # --- State Update (미분방정식 - Mean Reverting) ---
        # 현재 pH가 목표 pH를 향해 점진적으로 수렴
        diff = target_ph - s.ph
        s.ph += diff * (dt / tau_sec)

        # 🎯 [핵심 패치] 화학적 미세 노이즈: 기존 0.005 -> 0.001로 대폭 축소 (갑작스러운 튐 현상 방지)
        proc_sigma = 0.001
        noise = proc_sigma * math.sqrt(dt) * self.rng.gauss(0.0, 1.0)

        # 최종 안전장치: 아무리 노이즈가 누적되어도 5.5 ~ 9.0 사이를 절대 벗어날 수 없음
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
