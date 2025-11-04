# app/db/session.py
from __future__ import annotations

import importlib

from app.core.db import AsyncSessionLocal as _AsyncSessionLocal
from app.core.db import engine as _engine
from app.db.base import Base

engine = _engine
AsyncSessionLocal = _AsyncSessionLocal


async def init_db() -> None:
    importlib.import_module("app.models.command")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
