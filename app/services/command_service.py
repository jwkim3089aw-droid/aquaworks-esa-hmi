# app/services/command_service.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.command import CommandIn, CommandOut
from app.repositories.command_repo import CommandRepo
from app.models.command import Command
from app.adapters.plc.base import CommandPort

# -----------------------------
# 요청 스코프 서비스
# -----------------------------
@dataclass
class CommandService:
    session: AsyncSession
    repo: CommandRepo

    async def to_out(self, row: Command) -> CommandOut:
        return CommandOut.model_validate(row)  # Pydantic v2 from_attributes

    async def enqueue(self, body: CommandIn) -> CommandOut:
        # 멱등키 처리
        if body.idempotency_key:
            found = await self.repo.get_by_idempotency_key(self.session, body.idempotency_key)
            if found:
                return await self.to_out(found)

        row = await self.repo.insert(
            self.session,
            id=str(uuid4()),
            ts=datetime.now(timezone.utc),
            unit_id=body.unit_id,
            kind=body.kind,
            value=float(body.value),
            state="queued",
            dry_run=bool(body.dry_run),
            priority=int(body.priority or 0),
            idempotency_key=body.idempotency_key,
        )
        await self.session.commit()
        return await self.to_out(row)

# -----------------------------
# 백그라운드 매니저
# -----------------------------
class CommandManager:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None

    def start(self, port: CommandPort, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._runner(port, sessionmaker))

    async def _runner(self, port: CommandPort, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        repo = CommandRepo()
        try:
            while True:
                async with sessionmaker() as session:
                    rows = await repo.list_queued(session, limit=50)
                    for r in rows:
                        # 전송 전 상태 마킹
                        r.state = "sending"
                        await session.flush()
                        await session.commit()

                        try:
                            await port.send(kind=r.kind, value=r.value, unit_id=r.unit_id)
                            r.state = "done"
                        except Exception:
                            r.state = "failed"

                        await session.flush()
                        await session.commit()

                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            pass

# -----------------------------
# 싱글턴 팩토리
# -----------------------------
_manager: Optional[CommandManager] = None

def get_command_service() -> CommandManager:
    global _manager
    if _manager is None:
        _manager = CommandManager()
    return _manager
