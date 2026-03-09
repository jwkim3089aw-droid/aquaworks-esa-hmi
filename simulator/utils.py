# simulator/utils.py
from __future__ import annotations

import math
from typing import Final

CONST_G: Final[float] = 9.80665
CONST_P_ATM: Final[float] = 101325.0
CONST_RHO_WATER: Final[float] = 998.0
CP_WATER_J_PER_KG_K: Final[float] = 4180.0


def clamp(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def lag_filter(current: float, target: float, dt: float, tau: float) -> float:
    """First-order lag (exact discrete-time for constant target over dt)."""
    if tau <= 1e-9 or dt <= 0:
        return target
    alpha = 1.0 - math.exp(-dt / tau)
    return current + alpha * (target - current)


def sigmoid(x: float, k: float = 6.0) -> float:
    # numerically stable sigmoid
    if x >= 0:
        z = math.exp(-k * x)
        return 1.0 / (1.0 + z)
    z = math.exp(k * x)
    return z / (1.0 + z)


def calc_do_saturation_mgL(temp_c: float, depth_m: float) -> float:
    """
    DO saturation (mg/L) with temperature approximation + pressure correction by depth.
    NOTE: This is a pragmatic simulator formula (not a calibrated scientific standard).
    """
    T = temp_c
    fresh_sat = 14.652 - 0.41022 * T + 0.0079910 * T**2 - 0.000077774 * T**3
    fresh_sat = max(fresh_sat, 0.1)

    h = max(depth_m, 0.0)
    p_abs = CONST_P_ATM + CONST_RHO_WATER * CONST_G * h
    return fresh_sat * (p_abs / CONST_P_ATM)
