# app/workers/ai/config.py
import os
from pathlib import Path
from pydantic import BaseModel, Field

BASE_PATH = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_PATH / ".data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_is_windows = os.name == "nt"
_default_strict = "0" if _is_windows else "1"

STRICT_DURABILITY = os.getenv("STRICT_DURABILITY", _default_strict) == "1"
STRICT_DIRSYNC = os.getenv("STRICT_DIRSYNC", "1") == "1"

if _is_windows and STRICT_DURABILITY:
    raise RuntimeError(
        "STRICT_DURABILITY=1 on Windows cannot guarantee DB-grade durability. "
        "Set STRICT_DURABILITY=0 or run on POSIX filesystem."
    )


class SystemConfig(BaseModel):
    name: str = "ESA_Final_Product"
    air_start_hz: float = Field(default=28.0, ge=0.0, le=60.0)
    min_hz: float = Field(default=15.0, ge=0.0)
    max_hz: float = Field(default=50.0, ge=0.0, le=60.0)
    dt: float = 2.0
    base_valve_pos: float = 80.0
    batch_size: int = 64
    memory_capacity: int = 50000
    learning_rate: float = 0.0003
    train_mode: bool = True


SITE = SystemConfig()
