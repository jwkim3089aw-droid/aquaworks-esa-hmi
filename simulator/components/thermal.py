# simulator/components/thermal.py
from __future__ import annotations

from simulator.config import SystemSpec
from simulator.state import ModelState
from simulator.utils import CONST_RHO_WATER, CP_WATER_J_PER_KG_K
from simulator.numerics.integrator import rk4_scalar


class ThermalModel:
    def __init__(self, system: SystemSpec):
        self.sys = system
        self.mass_kg = system.tank_volume_m3 * CONST_RHO_WATER

    def step(self, dt: float, state: ModelState) -> None:
        sys = self.sys

        # energy (kWh)
        state.energy_kwh += state.power_kw * (dt / 3600.0)

        if self.mass_kg <= 0:
            return

        power_w = state.power_kw * 1000.0
        q_gain_w = power_w * sys.heat_fraction

        def dTdt(temp_c: float, _t_offset: float) -> float:
            q_loss_w = sys.ua_w_per_k * (temp_c - sys.ambient_temp_c)
            q_net = q_gain_w - q_loss_w
            return q_net / (self.mass_kg * CP_WATER_J_PER_KG_K)

        state.temp_c = rk4_scalar(state.temp_c, dt, dTdt)
