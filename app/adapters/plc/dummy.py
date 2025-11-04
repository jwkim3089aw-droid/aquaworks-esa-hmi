# app/adapters/plc/dummy.py
from __future__ import annotations
import asyncio
from typing import Optional
# from .base import CommandPort  # [REMOVED] Pylance unused import

class DummyCommandPort:
    async def send(self, kind: str, value: float, unit_id: Optional[str] = None) -> None:
        await asyncio.sleep(0.01)
        print(f"[DUMMY PORT] kind={kind} value={value} unit_id={unit_id}")
