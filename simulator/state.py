# simulator/state.py
from __future__ import annotations

import time
from pydantic import BaseModel, Field, ConfigDict


class ControlInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    pump_hz: float = Field(0.0, ge=0.0, le=120.0)
    valve_open_pct: float = Field(0.0, ge=0.0, le=100.0)


def _controls() -> ControlInput:
    return ControlInput.model_validate({})


class ModelState(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        validate_assignment=False,
    )

    wall_timestamp: float = Field(default_factory=time.time)
    controls: ControlInput = Field(default_factory=_controls)

    # Hydraulics
    flow_m3h: float = 0.0
    head_m: float = 0.0
    power_kw: float = 0.0

    # Air / ejector
    air_flow_lpm: float = 0.0
    suction_pressure_kpa: float = 0.0
    efficiency: float = 0.0

    # Water quality
    do_mgL: float = 5.0
    mlss_true_mgL: float = 3000.0
    mlss: float = 3000.0
    ph: float = 7.0

    # Thermal & energy
    temp_c: float = 20.0
    energy_kwh: float = 0.0

    # Environment
    sim_hour: float = 9.0
