# app/api/v1/commands/air.py
from __future__ import annotations

from typing import Annotated, TYPE_CHECKING, Any
from collections.abc import AsyncGenerator, Coroutine

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.command import CommandIn, CommandOut
from app.services.command_service import CommandService
from app.repositories.command_repo import CommandRepo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    def get_session() -> Coroutine[Any, Any, AsyncGenerator[_AsyncSession, None]]: ...
else:
    from app.core.db import get_session

router = APIRouter(prefix="/api/v1/air", tags=["air"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

def get_service(session: SessionDep) -> CommandService:
    return CommandService(session=session, repo=CommandRepo())

@router.post("/setpoint", response_model=CommandOut)
async def air_setpoint(cmd: CommandIn, svc: Annotated[CommandService, Depends(get_service)]) -> CommandOut:
    return await svc.enqueue(cmd)
