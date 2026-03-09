# simulator/components/ejector.py
from __future__ import annotations

import math

from simulator.config import EjectorSpec
from simulator.state import ModelState, ControlInput
from simulator.utils import clamp, lag_filter, sigmoid


class EjectorModel:
    def __init__(self, ejector: EjectorSpec):
        self.ej = ejector

    def step(self, dt: float, state: ModelState, controls: ControlInput) -> None:
        ej = self.ej

        if state.flow_m3h <= 0.1:
            state.air_flow_lpm = lag_filter(state.air_flow_lpm, 0.0, dt, ej.tau_air_s)
            state.suction_pressure_kpa = 0.0
            return

        q_m3s = state.flow_m3h / 3600.0
        throat_area = math.pi * (ej.throat_diameter_m / 2.0) ** 2
        v_throat = q_m3s / max(throat_area, 1e-12)

        v_norm = (v_throat - ej.v_min_m_s) / ej.v_span_m_s
        suction_enable = sigmoid(v_norm, k=6.0)

        valve_factor = clamp(controls.valve_open_pct / 100.0, 0.0, 1.0)

        mu_target = ej.mu_max * suction_enable * valve_factor * ej.suction_eff
        air_target_lpm = mu_target * q_m3s * 60000.0

        state.air_flow_lpm = lag_filter(state.air_flow_lpm, air_target_lpm, dt, ej.tau_air_s)
        state.suction_pressure_kpa = -101.3 * suction_enable * valve_factor
