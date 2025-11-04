# app/adapters/plc/base.py
from __future__ import annotations

from typing import Protocol


class CommandPort(Protocol):
    async def send(self, kind: str, value: float, unit_id: str | None = None) -> None: ...
