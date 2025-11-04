# app/core/db.py
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

s = get_settings()
DATABASE_URL: str = getattr(s, "DATABASE_URL", "sqlite+aiosqlite:///./.data/esa_hmi.db")

# sqlite면 디렉터리 보장
if DATABASE_URL.startswith("sqlite"):
    Path("./.data").mkdir(exist_ok=True)  # [ADDED]

engine = create_async_engine(
    DATABASE_URL,
    echo=bool(getattr(s, "SQL_ECHO", False)),
    future=True,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
