# app/api/v1/rtu_control.py
from __future__ import annotations

import time
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, AsyncSession as _AsyncSession

from app.core.db import engine
from app.stream.state import command_q

# 🚀 동적 설정을 읽기 위해 JSON 관리자 임포트
from app.core.device_config import get_device_config

router = APIRouter(prefix="/api/v1/rtu/{rtu_id}", tags=["rtu-control"])

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=_AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


CmdStatus = Literal["PENDING", "RUNNING", "DONE", "FAILED", "EXPIRED", "CANCELED"]


class WriteCmdIn(BaseModel):
    addr: int
    value: float
    requested_by: Optional[str] = None
    note: Optional[str] = None
    expire_sec: float = Field(5.0, ge=0.5, le=60.0)


class WriteCmdOut(BaseModel):
    id: int
    status: CmdStatus
    created_at: float
    expires_at: float


class WriteCmdRow(BaseModel):
    id: int
    created_at: float
    expires_at: float
    requested_by: Optional[str] = None
    note: Optional[str] = None
    addr: int
    value: float
    status: str
    started_at: Optional[float] = None
    executed_at: Optional[float] = None
    latency_ms: Optional[float] = None
    ok: Optional[bool] = None
    error: Optional[str] = None


@router.post("/write", response_model=WriteCmdOut)
async def enqueue_write_cmd(rtu_id: int, body: WriteCmdIn, db: AsyncSession = Depends(get_db)):
    now = time.time()
    exp = now + float(body.expire_sec)

    await db.execute(
        text(
            """
            INSERT INTO rtu_write_cmd (
              rtu_id, created_at, expires_at, requested_by, note, addr, value, status
            ) VALUES (
              :rtu_id, :created_at, :expires_at, :requested_by, :note, :addr, :value, 'PENDING'
            )
            """
        ),
        {
            "rtu_id": rtu_id,
            "created_at": now,
            "expires_at": exp,
            "requested_by": body.requested_by,
            "note": body.note,
            "addr": int(body.addr),
            "value": float(body.value),
        },
    )
    await db.commit()

    rid = await db.execute(
        text("SELECT id FROM rtu_write_cmd WHERE rtu_id=:rtu ORDER BY id DESC LIMIT 1"),
        {"rtu": rtu_id},
    )
    raw_id = rid.scalar()

    if raw_id is None:
        raise HTTPException(status_code=500, detail="Database insert failed")

    cmd_id = int(raw_id)

    # 🚀 [완전 동적 아키텍처] 하드코딩 완전 제거!
    config = get_device_config(rtu_id)
    tags = config.get("tags", {})

    cmd_name = None
    # 1. UI가 보낸 주소(body.addr)가 무슨 태그인지 JSON에서 역추적합니다.
    for key, tag_info in tags.items():
        if tag_info.get("mb_addr") == body.addr:
            cmd_name = key
            break

    # 2. JSON에 등록되지 않은 미래의 신규/임시 주소라도 거부하지 않고 그대로 캡슐화
    if not cmd_name:
        cmd_name = f"raw_{body.addr}"

    await command_q.put((rtu_id, cmd_name, float(body.value)))

    return WriteCmdOut(id=cmd_id, status="PENDING", created_at=now, expires_at=exp)


@router.get("/writes", response_model=List[WriteCmdRow])
async def list_write_cmds(
    rtu_id: int,
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if status:
        res = await db.execute(
            text(
                "SELECT * FROM rtu_write_cmd WHERE rtu_id=:rtu AND status=:st ORDER BY id DESC LIMIT :l"
            ),
            {"rtu": rtu_id, "st": status, "l": limit},
        )
    else:
        res = await db.execute(
            text("SELECT * FROM rtu_write_cmd WHERE rtu_id=:rtu ORDER BY id DESC LIMIT :l"),
            {"rtu": rtu_id, "l": limit},
        )

    out = []
    for r in res.mappings().all():
        d = dict(r)
        raw_ok = d.get("ok")
        d["ok"] = bool(raw_ok) if raw_ok is not None else None
        out.append(WriteCmdRow(**d))

    return out


@router.post("/write/{cmd_id}/cancel")
async def cancel_write_cmd(rtu_id: int, cmd_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        text(
            """
            UPDATE rtu_write_cmd
            SET status='CANCELED', executed_at=:now, ok=0, error='canceled'
            WHERE rtu_id=:rtu AND id=:id AND status='PENDING'
            """
        ),
        {"rtu": rtu_id, "id": cmd_id, "now": time.time()},
    )
    await db.commit()
    return {"ok": bool(getattr(res, "rowcount", 0) or 0)}
