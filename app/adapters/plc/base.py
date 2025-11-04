# app/adapters/plc/base.py
from __future__ import annotations
from typing import Protocol, Optional

class CommandPort(Protocol):
    async def send(self, kind: str, value: float, unit_id: Optional[str] = None) -> None: ...
