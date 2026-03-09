# simulator/config.py
from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict, model_validator


class BaseConfig(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_default=True,
        allow_inf_nan=False,
    )


class PumpSpec(BaseConfig):
    rated_hz: float = Field(60.0, gt=0)
    min_hz: float = Field(15.0, ge=0)
    rated_flow_m3h: float = Field(30.0, gt=0)
    rated_head_m: float = Field(18.0, gt=0)
    shutoff_head_m: float = Field(25.0, gt=0)
    rated_power_kw: float = Field(3.7, gt=0)

    tau_flow_s: float = Field(1.2, ge=0)
    tau_power_s: float = Field(0.8, ge=0)

    @model_validator(mode="after")
    def check_head_physics(self) -> "PumpSpec":
        if self.shutoff_head_m <= self.rated_head_m:
            raise ValueError("shutoff_head_m must be > rated_head_m.")
        if self.min_hz > self.rated_hz:
            raise ValueError("min_hz must be <= rated_hz.")
        return self


class EjectorSpec(BaseConfig):
    throat_diameter_m: float = Field(0.03, gt=0)
    v_min_m_s: float = Field(5.0, ge=0)
    v_span_m_s: float = Field(6.0, gt=0)
    mu_max: float = Field(1.3, ge=0)

    suction_eff: float = Field(0.85, ge=0.0, le=1.0)
    tau_air_s: float = Field(1.5, ge=0)

    submergence_m: float = Field(1.5, ge=0)
    backpressure_scale_kpa: float = Field(30.0, ge=0)


class AerationSpec(BaseConfig):
    kla20_ref_per_hr: float = Field(10.0, ge=0)
    ref_air_lpm: float = Field(500.0, gt=0)
    ref_water_m3h: float = Field(30.0, gt=0)
    theta_kla: float = Field(1.024, gt=0)

    our_base_mgL_hr: float = Field(20.0, ge=0)
    theta_our: float = Field(1.07, gt=0)

    do_noise_std: float = Field(0.01, ge=0)
    exp_air: float = Field(0.7, ge=0)
    exp_water: float = Field(0.3, ge=0)
    ratio_eps: float = Field(1e-6, gt=0)


class SystemSpec(BaseConfig):
    tank_volume_m3: float = Field(10.0, gt=0)
    static_head_m: float = Field(2.0, ge=0)

    k_loss_factor: float = Field(0.0, ge=0)
    auto_calibrate: bool = True

    ambient_temp_c: float = Field(20.0)
    heat_fraction: float = Field(0.35, ge=0.0, le=1.0)
    ua_w_per_k: float = Field(120.0, ge=0)

    do_depth_m: float = Field(1.0, ge=0)


# -------------------------------------------------------------------
# Pylance-friendly factories:
# Pylance sometimes misreads BaseModel() constructor signature.
# Using model_validate({}) makes it unambiguous for the type-checker.
# -------------------------------------------------------------------
def _pump_spec() -> PumpSpec:
    return PumpSpec.model_validate({})


def _ejector_spec() -> EjectorSpec:
    return EjectorSpec.model_validate({})


def _aeration_spec() -> AerationSpec:
    return AerationSpec.model_validate({})


def _system_spec() -> SystemSpec:
    return SystemSpec.model_validate({})


class SimulationConfig(BaseConfig):
    time_scale: float = Field(1.0, gt=0.0)
    max_dt: float = Field(0.5, gt=0.0)
    max_real_dt: float = Field(1.0, gt=0.0)
    rng_seed: int = Field(42)

    pump: PumpSpec = Field(default_factory=_pump_spec)
    ejector: EjectorSpec = Field(default_factory=_ejector_spec)
    aeration: AerationSpec = Field(default_factory=_aeration_spec)
    system: SystemSpec = Field(default_factory=_system_spec)
