# app/schemas/command.py
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CommandIn(BaseModel):
    unit_id: str | None = None
    kind: str
    value: float
    dry_run: bool = False
    priority: int = 0
    idempotency_key: str | None = None


class CommandOut(BaseModel):
    id: str
    ts: datetime
    unit_id: str | None
    kind: str
    value: float
    state: str
    dry_run: bool
    priority: int
    idempotency_key: str | None = None

    model_config = ConfigDict(from_attributes=True)
