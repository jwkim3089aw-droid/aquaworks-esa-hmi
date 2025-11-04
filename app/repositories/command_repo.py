# app/repositories/command_repo.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.engine import ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command import Command


class CommandRepo:
    async def insert(
        self,
        session: AsyncSession,
        *,
        id: str,
        ts: datetime,
        unit_id: str | None,
        kind: str,
        value: float,
        state: str,
        dry_run: bool,
        priority: int,
        idempotency_key: str | None,
    ) -> Command:
        row = Command(
            id=id,
            ts=ts,
            unit_id=unit_id,
            kind=kind,
            value=value,
            state=state,
            dry_run=dry_run,
            priority=priority,
            idempotency_key=idempotency_key,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return row

    async def get_by_idempotency_key(self, session: AsyncSession, key: str) -> Command | None:
        stmt = select(Command).where(Command.idempotency_key == key)
        res = await session.execute(stmt)
        rows: ScalarResult[Command] = res.scalars()
        return rows.first()

    async def get_by_id(self, session: AsyncSession, id: str) -> Command | None:
        stmt = select(Command).where(Command.id == id)
        res = await session.execute(stmt)
        rows: ScalarResult[Command] = res.scalars()
        return rows.first()

    async def list_recent(self, session: AsyncSession, limit: int = 50) -> list[Command]:
        stmt = select(Command).order_by(Command.ts.desc()).limit(limit)
        res = await session.execute(stmt)
        rows: ScalarResult[Command] = res.scalars()
        return list(rows.all())

    # 큐에 쌓인 항목 조회
    async def list_queued(self, session: AsyncSession, limit: int = 50) -> list[Command]:
        stmt = (
            select(Command).where(Command.state == "queued").order_by(Command.ts.asc()).limit(limit)
        )
        res = await session.execute(stmt)
        rows: ScalarResult[Command] = res.scalars()
        return list(rows.all())
