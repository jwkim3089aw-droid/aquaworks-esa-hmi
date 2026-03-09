# simulator/components/aeration.py
from __future__ import annotations

import math
import random
from typing import Callable

from simulator.config import AerationSpec, SystemSpec
from simulator.state import ModelState
from simulator.utils import clamp, calc_do_saturation_mgL
from simulator.numerics.integrator import rk4_scalar


class AerationModel:
    def __init__(self, aer: AerationSpec, system: SystemSpec, rng: random.Random):
        self.aer = aer
        self.sys = system
        self.rng = rng

    def _our_mgL_hr(self, temp_c: float, sim_hour: float) -> float:
        aer = self.aer
        our_t = aer.our_base_mgL_hr * (aer.theta_our ** (temp_c - 20.0))
        hour_rad = (sim_hour - 12.0) * (math.pi / 12.0)
        load_factor = 1.0 + 0.3 * math.sin(hour_rad)
        return our_t * load_factor

    def _kla_per_hr(self, temp_c: float, flow_m3h: float, air_lpm: float) -> float:
        aer = self.aer
        # ratios with epsilon to avoid 0^exp dropping everything to 0
        air_ratio = max(air_lpm / aer.ref_air_lpm, aer.ratio_eps)
        water_ratio = max(flow_m3h / aer.ref_water_m3h, aer.ratio_eps)

        kla_20 = aer.kla20_ref_per_hr * (air_ratio**aer.exp_air) * (water_ratio**aer.exp_water)
        return kla_20 * (aer.theta_kla ** (temp_c - 20.0))

    def step(self, dt: float, state: ModelState) -> None:
        aer = self.aer
        sys = self.sys

        # precompute forcing variables
        flow = state.flow_m3h
        air = state.air_flow_lpm
        temp = state.temp_c
        sim_hour0 = state.sim_hour

        def dydt(do_value: float, t_offset_s: float) -> float:
            # allow diurnal forcing inside the step (small but “more correct”)
            sim_hour = (sim_hour0 + t_offset_s / 3600.0) % 24.0
            do_sat = calc_do_saturation_mgL(temp, sys.do_depth_m)

            kla_hr = self._kla_per_hr(temp, flow, air)
            kla_s = kla_hr / 3600.0

            our_hr = self._our_mgL_hr(temp, sim_hour)
            our_s = our_hr / 3600.0

            return kla_s * (do_sat - do_value) - our_s

        do_next = rk4_scalar(state.do_mgL, dt, dydt)

        # noise (optional) - reproducible via injected rng
        if aer.do_noise_std > 0.0:
            do_next += self.rng.gauss(0.0, aer.do_noise_std) * math.sqrt(dt)

        do_sat_end = calc_do_saturation_mgL(temp, sys.do_depth_m)
        state.do_mgL = clamp(do_next, 0.0, do_sat_end)
