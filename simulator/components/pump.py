# simulator/components/pump.py
from __future__ import annotations

import math
from dataclasses import dataclass

from simulator.config import PumpSpec, SystemSpec
from simulator.state import ModelState, ControlInput
from simulator.utils import CONST_G, CONST_RHO_WATER, clamp, lag_filter


@dataclass
class PumpCache:
    pump_h0: float
    pump_a: float
    sys_k: float
    ref_efficiency: float
    rated_q_m3s: float


class PumpModel:
    def __init__(self, pump: PumpSpec, system: SystemSpec):
        self.pump = pump
        self.system = system
        self.cache = self._build_cache(pump, system)

    @staticmethod
    def _build_cache(p: PumpSpec, sys: SystemSpec) -> PumpCache:
        q_rated_s = p.rated_flow_m3h / 3600.0
        pump_h0 = p.shutoff_head_m

        numerator = max(p.shutoff_head_m - p.rated_head_m, 0.0)
        pump_a = numerator / (q_rated_s**2) if q_rated_s > 1e-12 else 0.0

        if sys.auto_calibrate or sys.k_loss_factor <= 0:
            h_friction = max(p.rated_head_m - sys.static_head_m, 0.0)
            sys_k = h_friction / (q_rated_s**2) if q_rated_s > 1e-12 else 0.0
        else:
            sys_k = sys.k_loss_factor

        water_power_w = CONST_RHO_WATER * CONST_G * q_rated_s * p.rated_head_m
        shaft_power_w = p.rated_power_kw * 1000.0
        ref_eff = clamp(water_power_w / max(shaft_power_w, 1e-9), 0.1, 0.85)

        return PumpCache(
            pump_h0=pump_h0,
            pump_a=pump_a,
            sys_k=sys_k,
            ref_efficiency=ref_eff,
            rated_q_m3s=q_rated_s,
        )

    def step(self, dt: float, state: ModelState, controls: ControlInput) -> None:
        p = self.pump
        sys = self.system
        c = self.cache

        # target hz with cutoff
        target_hz = clamp(controls.pump_hz, 0.0, p.rated_hz)
        if 0.0 < target_hz < p.min_hz:
            target_hz = 0.0

        speed_ratio = target_hz / p.rated_hz if p.rated_hz > 0 else 0.0

        # operating point solve
        if speed_ratio <= 0.0:
            q_target_m3s = 0.0
        else:
            h_pump_static = c.pump_h0 * (speed_ratio**2)
            driving_head = h_pump_static - sys.static_head_m
            total_impedance = c.pump_a + c.sys_k

            if driving_head <= 0.0 or total_impedance <= 1e-12:
                q_target_m3s = 0.0
            else:
                q_target_m3s = math.sqrt(driving_head / total_impedance)

            # physical-ish flow cutoff
            q_max = c.rated_q_m3s * (speed_ratio * 1.2)
            q_target_m3s = min(q_target_m3s, q_max)

        # inertia (exact lag)
        current_q_m3s = state.flow_m3h / 3600.0
        next_q_m3s = lag_filter(current_q_m3s, q_target_m3s, dt, p.tau_flow_s)

        # head back-calc
        if next_q_m3s > 1e-12:
            head = max((c.pump_h0 * speed_ratio**2) - (c.pump_a * next_q_m3s**2), 0.0)
        else:
            head = 0.0

        # power
        if next_q_m3s > 1e-12 and head > 1e-9:
            hydraulic_w = CONST_RHO_WATER * CONST_G * next_q_m3s * head
            eff_factor = math.sqrt(clamp(next_q_m3s / max(c.rated_q_m3s, 1e-9), 0.1, 1.0))
            eff = c.ref_efficiency * eff_factor
            target_kw = (hydraulic_w / max(eff, 1e-9)) / 1000.0
        else:
            eff = 0.0
            target_kw = 0.0

        state.flow_m3h = next_q_m3s * 3600.0
        state.head_m = head
        state.efficiency = eff
        state.power_kw = lag_filter(state.power_kw, target_kw, dt, p.tau_power_s)
