# app/core/auth.py
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel
from fastapi import HTTPException, status

class AdminUser(BaseModel):
    id: str
    role: Literal["admin"]

async def get_current_admin() -> AdminUser:
    # TODO: 실제 인증 로직으로 교체(JWT 쿠키 등)
    # 여기서는 임시 관리자 세션을 가정
    user = AdminUser(id="demo-admin", role="admin")
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return user

__all__ = ["AdminUser", "get_current_admin"]
