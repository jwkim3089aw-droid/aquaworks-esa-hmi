# app/api/v1/commands/router.py
from __future__ import annotations

from collections.abc import AsyncGenerator, Coroutine
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.command_repo import CommandRepo
from app.schemas.command import CommandIn, CommandOut
from app.services.command_service import CommandService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

    def get_session() -> Coroutine[Any, Any, AsyncGenerator[_AsyncSession, None]]: ...
else:
    from app.core.db import get_session

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_service(session: SessionDep) -> CommandService:
    return CommandService(session=session, repo=CommandRepo())


@router.post("", response_model=CommandOut)
async def enqueue(
    body: CommandIn, svc: Annotated[CommandService, Depends(get_service)]
) -> CommandOut:
    return await svc.enqueue(body)


@router.get("", response_model=list[CommandOut])
async def list_recent(svc: Annotated[CommandService, Depends(get_service)]) -> list[CommandOut]:
    rows = await svc.repo.list_recent(svc.session, limit=50)
    return [await svc.to_out(r) for r in rows]


@router.get("/{cmd_id}", response_model=CommandOut | None)
async def get_one(
    cmd_id: str, svc: Annotated[CommandService, Depends(get_service)]
) -> CommandOut | None:
    row = await svc.repo.get_by_id(svc.session, cmd_id)
    return await svc.to_out(row) if row else None
