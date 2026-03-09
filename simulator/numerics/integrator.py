# simulator/numerics/integrator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class StepStats:
    steps: int
    total_dt: float


def substep_integrate(
    dt_total: float, max_dt: float, step_fn: Callable[[float], None]
) -> StepStats:
    """
    Split dt_total into <= max_dt chunks and call step_fn(dt) for each.
    """
    if dt_total <= 0:
        return StepStats(steps=0, total_dt=0.0)

    steps = 0
    remaining = dt_total
    while remaining > 0:
        h = remaining if remaining <= max_dt else max_dt
        step_fn(h)
        remaining -= h
        steps += 1

    return StepStats(steps=steps, total_dt=dt_total)


def rk4_scalar(
    y0: float,
    dt: float,
    dydt: Callable[[float, float], float],
) -> float:
    """
    RK4 integrator for a scalar ODE:
      dy/dt = f(y, t_offset)
    t_offset is in seconds (0..dt), useful if you want time-varying forcing inside a step.
    """
    if dt <= 0:
        return y0

    k1 = dydt(y0, 0.0)
    k2 = dydt(y0 + 0.5 * dt * k1, 0.5 * dt)
    k3 = dydt(y0 + 0.5 * dt * k2, 0.5 * dt)
    k4 = dydt(y0 + dt * k3, dt)
    return y0 + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
