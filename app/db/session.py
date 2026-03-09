# app/db/session.py
from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator, Protocol, runtime_checkable, cast

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings  # pydantic-settings


@runtime_checkable
class _SettingsProto(Protocol):
    DB_URL: str
    DB_ECHO: bool


# get_settings() 반환형을 프로토콜로 명시적으로 캐스팅 → Pylance 타입오류 해소
S = cast(_SettingsProto, get_settings())


def _maybe_prepare_sqlite_dir(url: str) -> None:
    """sqlite+aiosqlite:/// 절대경로일 때 상위 폴더 자동 생성."""
    if url.startswith("sqlite+aiosqlite:///"):
        db_path = Path(url.replace("sqlite+aiosqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)


_maybe_prepare_sqlite_dir(S.DB_URL)

engine: AsyncEngine = create_async_engine(
    S.DB_URL,
    future=True,
    echo=S.DB_ECHO,
    pool_pre_ping=True,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends 에서 사용하는 AsyncSession DI."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """
    부팅 시 모델이 등록되어 있으면 create_all 수행.
    Alembic 사용 중이면 환경변수 DISABLE_CREATE_ALL=1 로 비활성화.
    """
    if os.getenv("DISABLE_CREATE_ALL") == "1":
        return

    try:
        from app.db import base as models  # Base(metadata) 를 보유한다고 가정

        Base = None
        for v in models.__dict__.values():
            if isinstance(v, type) and issubclass(v, DeclarativeBase):
                Base = v
                break

        if Base is not None:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    except Exception:
        # 모델 미정의/외부 마이그레이션 사용 시에도 앱이 동작하도록 무시
        pass


async def close_engine() -> None:
    await engine.dispose()
