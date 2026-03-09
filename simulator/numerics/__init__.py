# simulator/numerics/__init__.py
from simulator.numerics.integrator import substep_integrate, rk4_scalar, StepStats

__all__ = ["substep_integrate", "rk4_scalar", "StepStats"]
