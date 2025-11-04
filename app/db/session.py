# app/db/session.py
from __future__ import annotations
from app.core.db import engine as _engine, AsyncSessionLocal as _AsyncSessionLocal
from app.db.base import Base
import importlib

engine = _engine
AsyncSessionLocal = _AsyncSessionLocal

async def init_db() -> None:
    importlib.import_module("app.models.command")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
