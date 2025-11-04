# app/api/v1/commands/admin.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import get_current_admin, AdminUser

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

@router.get("/me")
async def whoami(_admin: Annotated[AdminUser, Depends(get_current_admin)]) -> dict[str, str]:
    return {"id": _admin.id, "role": _admin.role}
