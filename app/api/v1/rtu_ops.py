# app/api/v1/rtu_ops.py
from __future__ import annotations

import time
import json
from typing import Any, Optional, List, Literal, AsyncGenerator, cast, Mapping

from fastapi import APIRouter, Depends, Query, Body, Request
from pydantic import BaseModel
from sqlalchemy import text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, AsyncSession as _AsyncSession

from app.core.db import engine

# 🚀 [패치] 모든 URL Prefix에 장비 식별자 {rtu_id}를 필수로 받도록 변경
router = APIRouter(prefix="/api/v1/rtu/{rtu_id}", tags=["rtu-ops"])

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=_AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# -------------------------
# Models
# -------------------------
SessionCat = Literal["STALE", "DISCONNECTED"]
OverallKind = Literal["OK", "DISCONNECTED", "COMM_STALE", "PROCESS_STALE", "NO_DATA"]
UiColor = Literal["green", "yellow", "red", "gray"]
UiIcon = Literal["check", "plug", "clock", "x"]


class UiPack(BaseModel):
    severity: int
    status: OverallKind
    color: UiColor
    icon: UiIcon
    should_blink: bool
    badge_text: str
    detail_text: str
    tooltip: str
    proc_age_sec: Optional[float] = None
    proc_stale_sec: float
    comm_age_sec: Optional[float] = None
    comm_stale_sec: float
    connected: bool = False
    port: Optional[str] = None
    baudrate: Optional[int] = None
    unit_id: Optional[int] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    last_read_ms: Optional[float] = None
    last_write_ms: Optional[float] = None
    write_q_size: Optional[int] = None
    ingest_q_size: Optional[int] = None
    db_q_size: Optional[int] = None


class RTUAlarmRow(BaseModel):
    id: int
    ts: float
    event_type: str
    severity: int
    message: str
    port: Optional[str] = None
    baudrate: Optional[int] = None
    unit_id: Optional[int] = None
    age_sec: Optional[float] = None
    stale_threshold_sec: Optional[float] = None
    last_error: Optional[str] = None
    consecutive_failures: Optional[int] = None
    acked: bool = False
    acked_at: Optional[float] = None
    acked_by: Optional[str] = None
    ack_note: Optional[str] = None


class ActiveAlarmOut(BaseModel):
    category: Literal["STALE", "DISCONNECTED"]
    active: bool
    last_enter: Optional[RTUAlarmRow] = None
    last_exit_ts: Optional[float] = None


class AlarmSummaryOut(BaseModel):
    total: int
    unacked: int
    last_event_ts: Optional[float] = None
    active_stale: bool
    active_disconnected: bool


class RTUSessionRow(BaseModel):
    id: int
    category: str
    start_ts: float
    end_ts: Optional[float] = None
    duration_sec: Optional[float] = None
    acked: bool = False
    acked_at: Optional[float] = None
    acked_by: Optional[str] = None
    ack_note: Optional[str] = None
    port: Optional[str] = None
    baudrate: Optional[int] = None
    unit_id: Optional[int] = None
    last_error: Optional[str] = None
    consecutive_failures: Optional[int] = None


class AvailabilityOut(BaseModel):
    category: SessionCat
    window_from: float
    window_to: float
    window_sec: float
    downtime_sec_total: float
    uptime_sec_total: float
    availability_pct: float
    incident_count: int
    mttr_sec: float
    mtbf_sec: float
    active_incident: bool
    active_incident_age_sec: float = 0.0


class WriteDuringDowntimeKpiOut(BaseModel):
    category: SessionCat
    window_from: float
    window_to: float
    total_cmds: int
    cmds_in_downtime: int
    downtime_cmd_fail: int
    downtime_cmd_ok: int
    downtime_cmd_fail_rate_pct: float


class WriteCmdSummaryOut(BaseModel):
    pending: int = 0
    running: int = 0
    failed: int = 0
    done: int = 0
    expired: int = 0
    canceled: int = 0
    last_cmd_id: Optional[int] = None
    last_cmd_status: Optional[str] = None
    last_cmd_ok: Optional[bool] = None
    last_cmd_error: Optional[str] = None
    last_cmd_latency_ms: Optional[float] = None


class ActionOut(BaseModel):
    id: str
    label: str
    severity: int
    hint: str
    method: Literal["GET", "POST"]
    endpoint: str
    payload_example: Optional[dict] = None


class CleanupOut(BaseModel):
    ok: bool
    cutoff_ts: float
    deleted_alarm_log: int
    deleted_sessions: int
    deleted_write_cmd: int
    deleted_ack_audit: int


class SuperDashboardV2Out(BaseModel):
    ts: float
    ui: UiPack
    alarm_summary: AlarmSummaryOut
    active_alarms: List[ActiveAlarmOut]
    recent_alarms: List[RTUAlarmRow]
    active_sessions: List[RTUSessionRow]
    recent_sessions: List[RTUSessionRow]
    availability: List[AvailabilityOut]
    write_kpi: List[WriteDuringDowntimeKpiOut]
    write_summary: WriteCmdSummaryOut
    actions: List[ActionOut]


class AckAuditRow(BaseModel):
    id: int
    ts: float
    action: str
    actor: Optional[str] = None
    note: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    alarms_acked: int = 0
    sessions_acked: int = 0
    client_host: Optional[str] = None
    snapshot_before: Optional[str] = None
    snapshot_after: Optional[str] = None


# -------------------------
# Helpers
# -------------------------
async def _insert_ack_audit(
    db: AsyncSession,
    *,
    rtu_id: int,  # 🚀 [패치] rtu_id 추가
    action: str,
    actor: Optional[str],
    note: Optional[str],
    target_type: Optional[str],
    target_id: Optional[int],
    alarms_acked: int,
    sessions_acked: int,
    client_host: Optional[str],
    snapshot_before: dict[str, Any] | None = None,
    snapshot_after: dict[str, Any] | None = None,
) -> None:
    # 🚀 [패치] Audit 로그에도 해당 장비 소속 기록
    await db.execute(
        text(
            """
            INSERT INTO rtu_ack_audit(
              rtu_id, ts, action, actor, note, target_type, target_id,
              alarms_acked, sessions_acked, client_host,
              snapshot_before, snapshot_after
            ) VALUES (
              :rtu_id, :ts, :action, :actor, :note, :target_type, :target_id,
              :alarms_acked, :sessions_acked, :client_host,
              :before, :after
            )
            """
        ),
        {
            "rtu_id": rtu_id,
            "ts": time.time(),
            "action": action,
            "actor": actor,
            "note": note,
            "target_type": target_type,
            "target_id": target_id,
            "alarms_acked": int(alarms_acked),
            "sessions_acked": int(sessions_acked),
            "client_host": client_host,
            "before": (
                json.dumps(snapshot_before, ensure_ascii=False)
                if snapshot_before is not None
                else None
            ),
            "after": (
                json.dumps(snapshot_after, ensure_ascii=False)
                if snapshot_after is not None
                else None
            ),
        },
    )


async def _load_alarm_snapshot(db: AsyncSession, alarm_id: int) -> dict[str, Any] | None:
    r = await db.execute(text("SELECT * FROM rtu_alarm_log WHERE id=:id"), {"id": alarm_id})
    row = r.mappings().first()
    return dict(row) if row else None


async def _load_session_snapshot(db: AsyncSession, session_id: int) -> dict[str, Any] | None:
    r = await db.execute(text("SELECT * FROM rtu_alarm_session WHERE id=:id"), {"id": session_id})
    row = r.mappings().first()
    return dict(row) if row else None


async def _get_setting(db: AsyncSession, key: str, default: float) -> float:
    r = await db.execute(text("SELECT value FROM app_settings WHERE key=:k"), {"k": key})
    v = r.scalar()
    try:
        if v is None:
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _clip(a0: float, a1: float, b0: float, b1: float) -> float:
    s = max(a0, b0)
    e = min(a1, b1)
    return max(0.0, e - s)


def _as_float_opt(x: Any) -> Optional[float]:
    """Pylance 호환: Any 타입을 받아 float 또는 None 반환"""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _fmt_s(x: Optional[float]) -> str:
    return "unknown" if x is None else f"{x:.1f}s"


def _make_ui(
    *,
    overall: OverallKind,
    proc_age: Optional[float],
    proc_stale_sec: float,
    comm_age: Optional[float],
    comm_stale_sec: float,
    row: Optional[dict],
    connected_effective: bool,
) -> UiPack:
    port = (row or {}).get("port")
    baud = (row or {}).get("baudrate")
    unit = (row or {}).get("unit_id")
    last_err = (row or {}).get("last_error")

    raw_fails = (row or {}).get("consecutive_failures")
    fails = int(raw_fails) if raw_fails is not None else 0

    tooltip = (
        f"port={port} baud={baud} unit={unit} "
        f"proc_age={_fmt_s(proc_age)}(th={proc_stale_sec:.1f}s) "
        f"comm_age={_fmt_s(comm_age)}(th={comm_stale_sec:.1f}s) "
        f"failures={fails}" + (f" last_error={last_err}" if last_err else "")
    )

    def base(
        sev: int,
        st: OverallKind,
        color: UiColor,
        icon: UiIcon,
        blink: bool,
        badge: str,
        detail: str,
    ) -> UiPack:
        return UiPack(
            severity=sev,
            status=st,
            color=color,
            icon=icon,
            should_blink=blink,
            badge_text=badge,
            detail_text=detail,
            tooltip=tooltip,
            proc_age_sec=proc_age,
            proc_stale_sec=proc_stale_sec,
            comm_age_sec=comm_age,
            comm_stale_sec=comm_stale_sec,
            connected=connected_effective,
            port=port,
            baudrate=baud,
            unit_id=unit,
            last_error=last_err,
            consecutive_failures=fails,
            last_read_ms=(row or {}).get("last_read_ms"),
            last_write_ms=(row or {}).get("last_write_ms"),
            write_q_size=(row or {}).get("write_q_size"),
            ingest_q_size=(row or {}).get("ingest_q_size"),
            db_q_size=(row or {}).get("db_q_size"),
        )

    if overall == "NO_DATA":
        return base(
            1,
            overall,
            "gray",
            "x",
            False,
            "NO DATA",
            "상태 데이터 없음 (worker 미기동/테이블 미생성)",
        )
    if overall == "PROCESS_STALE":
        return base(
            3,
            overall,
            "red",
            "x",
            True,
            "WORKER DOWN",
            f"워커 heartbeat 지연: 마지막 갱신 {_fmt_s(proc_age)} (기준 {proc_stale_sec:.1f}s)",
        )
    if overall == "COMM_STALE":
        return base(
            3,
            overall,
            "red",
            "clock",
            True,
            "COMM STALE",
            f"통신 성공 지연: last_success {_fmt_s(comm_age)} (기준 {comm_stale_sec:.1f}s)",
        )
    if overall == "DISCONNECTED":
        return base(
            2, overall, "yellow", "plug", False, "DISCONNECTED", f"장비 연결 끊김 ({port}/{baud})"
        )
    return base(0, "OK", "green", "check", False, "OK", f"정상 통신 중 ({port}/{baud})")


async def _active_alarms(db: AsyncSession, rtu_id: int) -> List[ActiveAlarmOut]:  # 🚀 rtu_id 주입
    cats = [
        ("STALE", "STALE_ENTER", "STALE_EXIT"),
        ("DISCONNECTED", "DISCONNECTED_ENTER", "DISCONNECTED_EXIT"),
    ]
    out: List[ActiveAlarmOut] = []
    for cat_name, enter_t, exit_t in cats:
        category_lit = cast(Literal["STALE", "DISCONNECTED"], cat_name)
        re = await db.execute(
            text(
                "SELECT * FROM rtu_alarm_log WHERE rtu_id=:rtu AND event_type=:t ORDER BY ts DESC LIMIT 1"
            ),
            {"rtu": rtu_id, "t": enter_t},
        )
        enter_row = re.mappings().first()
        enter_ts = float(enter_row["ts"]) if enter_row else None
        rx = await db.execute(
            text(
                "SELECT ts FROM rtu_alarm_log WHERE rtu_id=:rtu AND event_type=:t ORDER BY ts DESC LIMIT 1"
            ),
            {"rtu": rtu_id, "t": exit_t},
        )
        exit_ts = rx.scalar()
        exit_ts = float(exit_ts) if exit_ts is not None else None
        active = False
        if enter_ts is not None:
            active = (exit_ts is None) or (enter_ts > exit_ts)
        last_enter = None
        if enter_row:
            d = dict(enter_row)
            d["acked"] = bool(d.get("acked", 0))
            last_enter = RTUAlarmRow(**d)
        out.append(
            ActiveAlarmOut(
                category=category_lit, active=active, last_enter=last_enter, last_exit_ts=exit_ts
            )
        )
    return out


async def _alarm_summary(
    db: AsyncSession, rtu_id: int, active: List[ActiveAlarmOut]
) -> AlarmSummaryOut:  # 🚀 rtu_id 주입
    t = int(
        (
            await db.execute(
                text("SELECT COUNT(*) FROM rtu_alarm_log WHERE rtu_id=:rtu"), {"rtu": rtu_id}
            )
        ).scalar()
        or 0
    )
    u = int(
        (
            await db.execute(
                text("SELECT COUNT(*) FROM rtu_alarm_log WHERE rtu_id=:rtu AND acked=0"),
                {"rtu": rtu_id},
            )
        ).scalar()
        or 0
    )
    last = (
        await db.execute(
            text("SELECT ts FROM rtu_alarm_log WHERE rtu_id=:rtu ORDER BY ts DESC LIMIT 1"),
            {"rtu": rtu_id},
        )
    ).scalar()
    last_ts = float(last) if last is not None else None
    return AlarmSummaryOut(
        total=t,
        unacked=u,
        last_event_ts=last_ts,
        active_stale=any(a.category == "STALE" and a.active for a in active),
        active_disconnected=any(a.category == "DISCONNECTED" and a.active for a in active),
    )


async def _recent_alarms(
    db: AsyncSession, rtu_id: int, limit: int
) -> List[RTUAlarmRow]:  # 🚀 rtu_id 주입
    res = await db.execute(
        text(
            "SELECT id, ts, event_type, severity, message, port, baudrate, unit_id, age_sec, stale_threshold_sec, last_error, consecutive_failures, acked, acked_at, acked_by, ack_note FROM rtu_alarm_log WHERE rtu_id=:rtu ORDER BY ts DESC LIMIT :limit"
        ),
        {"rtu": rtu_id, "limit": limit},
    )
    out = []
    for r in res.mappings().all():
        d = dict(r)
        d["acked"] = bool(d.get("acked", 0))
        out.append(RTUAlarmRow(**d))
    return out


async def _sessions(
    db: AsyncSession, rtu_id: int, limit: int  # 🚀 rtu_id 주입
) -> tuple[List[RTUSessionRow], List[RTUSessionRow]]:
    ra = await db.execute(
        text(
            "SELECT * FROM rtu_alarm_session WHERE rtu_id=:rtu AND end_ts IS NULL ORDER BY start_ts DESC LIMIT :l"
        ),
        {"rtu": rtu_id, "l": min(limit, 50)},
    )
    active_rows = [
        RTUSessionRow(**{**dict(r), "acked": bool(dict(r).get("acked", 0))})
        for r in ra.mappings().all()
    ]
    rr = await db.execute(
        text("SELECT * FROM rtu_alarm_session WHERE rtu_id=:rtu ORDER BY start_ts DESC LIMIT :l"),
        {"rtu": rtu_id, "l": limit},
    )
    recent_rows = [
        RTUSessionRow(**{**dict(r), "acked": bool(dict(r).get("acked", 0))})
        for r in rr.mappings().all()
    ]
    return active_rows, recent_rows


async def _availability(
    db: AsyncSession,
    *,
    rtu_id: int,
    days: int,
    category: SessionCat,
    include_active: bool,  # 🚀 rtu_id 주입
) -> AvailabilityOut:
    now = time.time()
    window_from = now - float(days) * 86400.0
    window_to = now
    window_sec = max(1.0, window_to - window_from)
    res = await db.execute(
        text(
            "SELECT start_ts, end_ts, duration_sec FROM rtu_alarm_session WHERE rtu_id=:rtu AND category=:cat AND start_ts < :to AND (end_ts IS NULL OR end_ts > :from) ORDER BY start_ts ASC"
        ),
        {"rtu": rtu_id, "cat": category, "from": window_from, "to": window_to},
    )
    rows = [dict(r) for r in res.mappings().all()]
    downtime = 0.0
    closed: List[float] = []
    active_incident = False
    active_age = 0.0
    for r in rows:
        s = float(r["start_ts"])
        e = float(r["end_ts"]) if r.get("end_ts") is not None else None
        if e is None:
            active_incident = True
            active_age = max(active_age, window_to - s)
            if include_active:
                downtime += _clip(s, window_to, window_from, window_to)
        else:
            downtime += _clip(s, e, window_from, window_to)
            dur = float(r["duration_sec"]) if r.get("duration_sec") is not None else max(0.0, e - s)
            closed.append(dur)
    uptime = max(0.0, window_sec - downtime)
    return AvailabilityOut(
        category=category,
        window_from=window_from,
        window_to=window_to,
        window_sec=window_sec,
        downtime_sec_total=downtime,
        uptime_sec_total=uptime,
        availability_pct=max(0.0, min(100.0, (uptime / window_sec) * 100.0)),
        incident_count=len(closed),
        mttr_sec=(sum(closed) / len(closed)) if closed else 0.0,
        mtbf_sec=(uptime / len(closed)) if closed else 0.0,
        active_incident=active_incident,
        active_incident_age_sec=active_age if active_incident else 0.0,
    )


async def _write_kpi(
    db: AsyncSession, *, rtu_id: int, days: int, category: SessionCat  # 🚀 rtu_id 주입
) -> WriteDuringDowntimeKpiOut:
    now = time.time()
    window_from = now - float(days) * 86400.0
    window_to = now
    sres = await db.execute(
        text(
            "SELECT start_ts, COALESCE(end_ts, :to) AS end_ts FROM rtu_alarm_session WHERE rtu_id=:rtu AND category=:cat AND start_ts < :to AND (end_ts IS NULL OR end_ts > :from) ORDER BY start_ts ASC"
        ),
        {"rtu": rtu_id, "cat": category, "from": window_from, "to": window_to},
    )
    sessions = [(float(r[0]), float(r[1])) for r in sres.all()]
    cres = await db.execute(
        text(
            "SELECT executed_at, ok FROM rtu_write_cmd WHERE rtu_id=:rtu AND executed_at IS NOT NULL AND executed_at >= :from AND executed_at <= :to AND status IN ('DONE','FAILED','EXPIRED','CANCELED')"
        ),
        {"rtu": rtu_id, "from": window_from, "to": window_to},
    )
    cmds = [(float(r[0]), r[1]) for r in cres.all()]
    in_dt = 0
    ok_cnt = 0
    fail_cnt = 0
    for t, ok in cmds:
        for s, e in sessions:
            if s <= t <= e:
                in_dt += 1
                if ok is not None:
                    if int(ok) == 1:
                        ok_cnt += 1
                    else:
                        fail_cnt += 1
                break
    denom = max(1, ok_cnt + fail_cnt)
    return WriteDuringDowntimeKpiOut(
        category=category,
        window_from=window_from,
        window_to=window_to,
        total_cmds=len(cmds),
        cmds_in_downtime=in_dt,
        downtime_cmd_fail=fail_cnt,
        downtime_cmd_ok=ok_cnt,
        downtime_cmd_fail_rate_pct=(fail_cnt / denom) * 100.0,
    )


async def _write_summary(db: AsyncSession, rtu_id: int) -> WriteCmdSummaryOut:  # 🚀 rtu_id 주입
    res = await db.execute(
        text("SELECT status, COUNT(*) AS c FROM rtu_write_cmd WHERE rtu_id=:rtu GROUP BY status"),
        {"rtu": rtu_id},
    )
    counts = {str(r[0]): int(r[1]) for r in res.all()}
    r2 = await db.execute(
        text("SELECT * FROM rtu_write_cmd WHERE rtu_id=:rtu ORDER BY id DESC LIMIT 1"),
        {"rtu": rtu_id},
    )
    row = r2.mappings().first()
    out = WriteCmdSummaryOut(
        pending=counts.get("PENDING", 0),
        running=counts.get("RUNNING", 0),
        failed=counts.get("FAILED", 0),
        done=counts.get("DONE", 0),
        expired=counts.get("EXPIRED", 0),
        canceled=counts.get("CANCELED", 0),
    )
    if row:
        d = dict(row)
        raw_id = d.get("id")
        raw_ok = d.get("ok")
        out.last_cmd_id = int(raw_id) if raw_id is not None else None
        out.last_cmd_status = d.get("status")
        out.last_cmd_ok = bool(raw_ok) if raw_ok is not None else None
        out.last_cmd_error = d.get("error")
        out.last_cmd_latency_ms = d.get("latency_ms")
    return out


# -------------------------
# endpoints
# -------------------------
@router.get("/availability", response_model=AvailabilityOut)
async def get_availability(
    rtu_id: int,  # 🚀 [패치] rtu_id 파라미터 추가
    days: int = Query(7, ge=1, le=180),
    category: SessionCat = Query("STALE"),
    include_active: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    return await _availability(
        db, rtu_id=rtu_id, days=days, category=category, include_active=include_active
    )


@router.get("/kpi/write-during-downtime", response_model=WriteDuringDowntimeKpiOut)
async def get_write_during_downtime(
    rtu_id: int,  # 🚀 [패치] rtu_id 파라미터 추가
    days: int = Query(7, ge=1, le=180),
    category: SessionCat = Query("STALE"),
    db: AsyncSession = Depends(get_db),
):
    return await _write_kpi(db, rtu_id=rtu_id, days=days, category=category)


@router.post("/cleanup", response_model=CleanupOut)
async def cleanup_retention(
    rtu_id: int,  # 🚀 [패치] rtu_id 파라미터 추가
    retention_days: int = Query(30, ge=1, le=365),
    dry_run: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    now = time.time()
    cutoff = now - float(retention_days) * 86400.0
    c1 = int(
        (
            await db.execute(
                text("SELECT COUNT(*) FROM rtu_alarm_log WHERE rtu_id=:rtu AND ts < :c"),
                {"rtu": rtu_id, "c": cutoff},
            )
        ).scalar()
        or 0
    )
    c2 = int(
        (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM rtu_alarm_session WHERE rtu_id=:rtu AND end_ts IS NOT NULL AND end_ts < :c"
                ),
                {"rtu": rtu_id, "c": cutoff},
            )
        ).scalar()
        or 0
    )
    c3 = int(
        (
            await db.execute(
                text("SELECT COUNT(*) FROM rtu_write_cmd WHERE rtu_id=:rtu AND created_at < :c"),
                {"rtu": rtu_id, "c": cutoff},
            )
        ).scalar()
        or 0
    )
    c4 = int(
        (
            await db.execute(
                text("SELECT COUNT(*) FROM rtu_ack_audit WHERE rtu_id=:rtu AND ts < :c"),
                {"rtu": rtu_id, "c": cutoff},
            )
        ).scalar()
        or 0
    )
    if dry_run:
        return CleanupOut(
            ok=True,
            cutoff_ts=cutoff,
            deleted_alarm_log=c1,
            deleted_sessions=c2,
            deleted_write_cmd=c3,
            deleted_ack_audit=c4,
        )
    r1 = await db.execute(
        text("DELETE FROM rtu_alarm_log WHERE rtu_id=:rtu AND ts < :c"),
        {"rtu": rtu_id, "c": cutoff},
    )
    r2 = await db.execute(
        text(
            "DELETE FROM rtu_alarm_session WHERE rtu_id=:rtu AND end_ts IS NOT NULL AND end_ts < :c"
        ),
        {"rtu": rtu_id, "c": cutoff},
    )
    r3 = await db.execute(
        text("DELETE FROM rtu_write_cmd WHERE rtu_id=:rtu AND created_at < :c"),
        {"rtu": rtu_id, "c": cutoff},
    )
    r4 = await db.execute(
        text("DELETE FROM rtu_ack_audit WHERE rtu_id=:rtu AND ts < :c"),
        {"rtu": rtu_id, "c": cutoff},
    )
    await db.commit()
    return CleanupOut(
        ok=True,
        cutoff_ts=cutoff,
        deleted_alarm_log=int(getattr(r1, "rowcount", 0) or 0),
        deleted_sessions=int(getattr(r2, "rowcount", 0) or 0),
        deleted_write_cmd=int(getattr(r3, "rowcount", 0) or 0),
        deleted_ack_audit=int(getattr(r4, "rowcount", 0) or 0),
    )


@router.get("/super-dashboard-v2", response_model=SuperDashboardV2Out)
async def super_dashboard_v2(
    rtu_id: int,  # 🚀 [패치] rtu_id 파라미터 추가
    comm_stale_sec: Optional[float] = Query(None, ge=0.5, le=120.0),
    proc_stale_sec: Optional[float] = Query(None, ge=0.5, le=120.0),
    recent_alarm_limit: int = Query(50, ge=1, le=200),
    session_limit: int = Query(50, ge=1, le=200),
    kpi_days: int = Query(7, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
):
    now = time.time()
    comm_sec = (
        float(comm_stale_sec)
        if comm_stale_sec is not None
        else await _get_setting(db, "rtu.comm_stale_sec", 5.0)
    )
    proc_sec = (
        float(proc_stale_sec)
        if proc_stale_sec is not None
        else await _get_setting(db, "rtu.proc_stale_sec", 3.0)
    )

    # 🚀 id=1 고정에서 :rtu_id 파라미터 바인딩으로 변경
    h = await db.execute(text("SELECT * FROM rtu_health WHERE id=:rtu_id"), {"rtu_id": rtu_id})
    row = h.mappings().first()
    rowd = dict(row) if row else None

    if not rowd:
        ui = _make_ui(
            overall="NO_DATA",
            proc_age=None,
            proc_stale_sec=proc_sec,
            comm_age=None,
            comm_stale_sec=comm_sec,
            row=None,
            connected_effective=False,
        )
    else:
        updated_at = _as_float_opt(rowd.get("updated_at"))
        last_ok = _as_float_opt(rowd.get("last_success_at"))
        proc_age = (now - updated_at) if updated_at is not None else None
        comm_age = (now - last_ok) if last_ok is not None else None
        proc_stale = (proc_age is None) or (proc_age > proc_sec)
        comm_stale = (comm_age is None) or (comm_age > comm_sec)
        connected_raw = bool(rowd.get("connected", 0))

        overall = (
            "PROCESS_STALE"
            if proc_stale
            else "COMM_STALE" if comm_stale else "OK" if connected_raw else "DISCONNECTED"
        )
        connected_effective = overall == "OK"
        ui = _make_ui(
            overall=overall,
            proc_age=proc_age,
            proc_stale_sec=proc_sec,
            comm_age=comm_age,
            comm_stale_sec=comm_sec,
            row=rowd,
            connected_effective=connected_effective,
        )

    active = await _active_alarms(db, rtu_id)
    summary = await _alarm_summary(db, rtu_id, active)
    recent = await _recent_alarms(db, rtu_id, recent_alarm_limit)
    active_sessions, recent_sessions = await _sessions(db, rtu_id, session_limit)
    availability = [
        await _availability(
            db, rtu_id=rtu_id, days=kpi_days, category="STALE", include_active=True
        ),
        await _availability(
            db, rtu_id=rtu_id, days=kpi_days, category="DISCONNECTED", include_active=True
        ),
    ]
    write_kpi = [
        await _write_kpi(db, rtu_id=rtu_id, days=kpi_days, category="STALE"),
        await _write_kpi(db, rtu_id=rtu_id, days=kpi_days, category="DISCONNECTED"),
    ]
    write_summary = await _write_summary(db, rtu_id)

    actions: List[ActionOut] = []
    if summary.unacked > 0:
        actions.append(
            ActionOut(
                id="ack-active",
                label="활성 알람 ACK",
                severity=1,
                hint="현재 진행 중(활성) 알람만 확인 처리하세요.",
                method="POST",
                endpoint=f"/api/v1/rtu/{rtu_id}/ack-active",  # 🚀 경로 변경
                payload_example={"acked_by": "operator", "ack_note": "확인"},
            )
        )
    if ui.status == "PROCESS_STALE":
        actions.append(
            ActionOut(
                id="restart-worker",
                label="워커/서비스 점검",
                severity=3,
                hint="워커 heartbeat 지연. 서비스 재시작 및 로그 점검.",
                method="GET",
                endpoint=f"/api/v1/rtu/{rtu_id}/super-dashboard-v2",  # 🚀 경로 변경
            )
        )
    elif ui.status == "COMM_STALE":
        actions.append(
            ActionOut(
                id="check-line",
                label="RS-485/COM/파라미터 점검",
                severity=3,
                hint="통신 성공 지연. 배선/COM/baud/unit 확인.",
                method="GET",
                endpoint=f"/api/v1/rtu/{rtu_id}/super-dashboard-v2",  # 🚀 경로 변경
            )
        )
    elif ui.status == "DISCONNECTED":
        actions.append(
            ActionOut(
                id="check-connection",
                label="연결 복구",
                severity=2,
                hint="장비 연결 끊김. 포트/전원/설정 확인.",
                method="GET",
                endpoint=f"/api/v1/rtu/{rtu_id}/super-dashboard-v2",  # 🚀 경로 변경
            )
        )
    if (write_summary.pending + write_summary.running) > 0:
        actions.append(
            ActionOut(
                id="check-write",
                label="제어 명령 병목 점검",
                severity=2,
                hint="대기/실행 중 write_cmd 존재. 워커/통신 상태 확인.",
                method="GET",
                endpoint=f"/api/v1/rtu/{rtu_id}/writes?limit=20",  # 🚀 경로 변경
            )
        )

    return SuperDashboardV2Out(
        ts=now,
        ui=ui,
        alarm_summary=summary,
        active_alarms=active,
        recent_alarms=recent,
        active_sessions=active_sessions,
        recent_sessions=recent_sessions,
        availability=availability,
        write_kpi=write_kpi,
        write_summary=write_summary,
        actions=actions,
    )


# -------------------------
# ACK endpoints
# -------------------------
class AckIn(BaseModel):
    acked_by: Optional[str] = "operator"
    ack_note: Optional[str] = None


class AckOut(BaseModel):
    ok: bool
    alarms_acked: int = 0
    sessions_acked: int = 0


@router.get("/ack-audit", response_model=List[AckAuditRow])
async def list_ack_audit(
    rtu_id: int,  # 🚀 [패치] rtu_id 파라미터 추가
    limit: int = Query(100, ge=1, le=500),
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    target_id: Optional[int] = Query(None),
    start_ts: Optional[float] = Query(None),
    end_ts: Optional[float] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    where = ["rtu_id = :rtu"]
    params: dict[str, Any] = {"rtu": rtu_id, "limit": limit}
    if actor:
        where.append("actor = :actor")
        params["actor"] = actor
    if action:
        where.append("action = :action")
        params["action"] = action
    if target_type:
        where.append("target_type = :target_type")
        params["target_type"] = target_type
    if target_id is not None:
        where.append("target_id = :target_id")
        params["target_id"] = target_id
    if start_ts is not None:
        where.append("ts >= :start_ts")
        params["start_ts"] = float(start_ts)
    if end_ts is not None:
        where.append("ts <= :end_ts")
        params["end_ts"] = float(end_ts)

    sql = f"SELECT id, ts, action, actor, note, target_type, target_id, alarms_acked, sessions_acked, client_host, snapshot_before, snapshot_after FROM rtu_ack_audit WHERE {' AND '.join(where)} ORDER BY ts DESC LIMIT :limit"
    res = await db.execute(text(sql), params)
    return [AckAuditRow(**dict(r)) for r in res.mappings().all()]


@router.post("/alarms/{alarm_id}/ack", response_model=AckOut)
async def ack_alarm(
    rtu_id: int,  # 🚀 [패치] rtu_id 파라미터 추가
    alarm_id: int,
    request: Request,
    body: AckIn = Body(default_factory=AckIn),
    db: AsyncSession = Depends(get_db),
):
    now = time.time()
    before_alarm = await _load_alarm_snapshot(db, alarm_id)
    r1 = await db.execute(
        text(
            "UPDATE rtu_alarm_log SET acked=1, acked_at=:now, acked_by=:by, ack_note=:note WHERE id=:id AND rtu_id=:rtu AND acked=0"
        ),
        {"now": now, "by": body.acked_by, "note": body.ack_note, "id": alarm_id, "rtu": rtu_id},
    )
    alarms_acked = int(getattr(r1, "rowcount", 0) or 0)
    r2 = await db.execute(
        text(
            "UPDATE rtu_alarm_session SET acked=1, acked_at=:now, acked_by=:by, ack_note=:note WHERE rtu_id=:rtu AND acked=0 AND (enter_alarm_id=:id OR exit_alarm_id=:id)"
        ),
        {"now": now, "by": body.acked_by, "note": body.ack_note, "id": alarm_id, "rtu": rtu_id},
    )
    sessions_acked = int(getattr(r2, "rowcount", 0) or 0)
    after_alarm = await _load_alarm_snapshot(db, alarm_id)
    sess_res = await db.execute(
        text(
            "SELECT id, category, start_ts, end_ts, acked FROM rtu_alarm_session WHERE rtu_id=:rtu AND (enter_alarm_id=:id OR exit_alarm_id=:id) ORDER BY start_ts DESC LIMIT 5"
        ),
        {"id": alarm_id, "rtu": rtu_id},
    )
    sess_rows = [dict(r) for r in sess_res.mappings().all()]
    await _insert_ack_audit(
        db,
        rtu_id=rtu_id,
        action="ACK_ALARM",
        actor=body.acked_by,
        note=body.ack_note,
        target_type="ALARM",
        target_id=alarm_id,
        alarms_acked=alarms_acked,
        sessions_acked=sessions_acked,
        client_host=request.client.host if request.client else None,
        snapshot_before={"alarm": before_alarm},
        snapshot_after={"alarm": after_alarm, "propagated_sessions_top5": sess_rows},
    )
    await db.commit()
    return AckOut(ok=True, alarms_acked=alarms_acked, sessions_acked=sessions_acked)


@router.post("/sessions/{session_id}/ack", response_model=AckOut)
async def ack_session(
    rtu_id: int,  # 🚀 [패치] rtu_id 파라미터 추가
    session_id: int,
    request: Request,
    body: AckIn = Body(default_factory=AckIn),
    ack_related_alarms: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    now = time.time()
    sres = await db.execute(
        text("SELECT * FROM rtu_alarm_session WHERE id=:id AND rtu_id=:rtu"),
        {"id": session_id, "rtu": rtu_id},
    )
    srow = sres.mappings().first()
    if not srow:
        return AckOut(ok=False)
    before_sess = dict(srow)
    cat = str(srow.get("category"))
    start_ts = _as_float_opt(srow.get("start_ts")) or time.time()
    end_ts = _as_float_opt(srow.get("end_ts")) or now
    enter_alarm_id = srow.get("enter_alarm_id")
    exit_alarm_id = srow.get("exit_alarm_id")

    r1 = await db.execute(
        text(
            "UPDATE rtu_alarm_session SET acked=1, acked_at=:now, acked_by=:by, ack_note=:note WHERE id=:id AND acked=0"
        ),
        {"now": now, "by": body.acked_by, "note": body.ack_note, "id": session_id},
    )
    sessions_acked = int(getattr(r1, "rowcount", 0) or 0)
    alarms_acked = 0
    acked_related_list = []
    if ack_related_alarms:
        ids = [i for i in [enter_alarm_id, exit_alarm_id] if i is not None]
        conds = []
        if ids:
            conds.append(f"id IN ({','.join(map(str, ids))})")
        ev_types = (
            ["STALE_ENTER", "STALE_EXIT"]
            if cat == "STALE"
            else ["DISCONNECTED_ENTER", "DISCONNECTED_EXIT"] if cat == "DISCONNECTED" else []
        )
        if ev_types:
            q_types = ",".join([f"'{t}'" for t in ev_types])
            conds.append(f"(ts >= {start_ts} AND ts <= {end_ts} AND event_type IN ({q_types}))")
        where = " OR ".join(conds) if conds else "FALSE"
        target_res = await db.execute(
            text(f"SELECT id FROM rtu_alarm_log WHERE rtu_id=:rtu AND acked=0 AND ({where})"),
            {"rtu": rtu_id},
        )
        target_ids = [r[0] for r in target_res.all()]
        if target_ids:
            r2 = await db.execute(
                text(
                    "UPDATE rtu_alarm_log SET acked=1, acked_at=:now, acked_by=:by, ack_note=:note WHERE id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)),
                {"now": now, "by": body.acked_by, "note": body.ack_note, "ids": target_ids},
            )
            alarms_acked = int(getattr(r2, "rowcount", 0) or 0)
            rel_res = await db.execute(
                text("SELECT * FROM rtu_alarm_log WHERE id IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": target_ids},
            )
            acked_related_list = [dict(r) for r in rel_res.mappings().all()]

    after_sess = await _load_session_snapshot(db, session_id)
    await _insert_ack_audit(
        db,
        rtu_id=rtu_id,
        action="ACK_SESSION",
        actor=body.acked_by,
        note=body.ack_note,
        target_type="SESSION",
        target_id=session_id,
        alarms_acked=alarms_acked,
        sessions_acked=sessions_acked,
        client_host=request.client.host if request.client else None,
        snapshot_before={"session": before_sess},
        snapshot_after={"session": after_sess, "related_alarms": acked_related_list},
    )
    await db.commit()
    return AckOut(ok=True, alarms_acked=alarms_acked, sessions_acked=sessions_acked)


@router.post("/ack-active", response_model=AckOut)
async def ack_active(
    rtu_id: int,  # 🚀 [패치] rtu_id 파라미터 추가
    request: Request,
    body: AckIn = Body(default_factory=AckIn),
    db: AsyncSession = Depends(get_db),
):
    now = time.time()
    res = await db.execute(
        text(
            "SELECT id, enter_alarm_id FROM rtu_alarm_session WHERE rtu_id=:rtu AND end_ts IS NULL"
        ),
        {"rtu": rtu_id},
    )
    rows = [dict(r) for r in res.mappings().all()]
    if not rows:
        return AckOut(ok=True)
    session_ids = [int(r["id"]) for r in rows]
    alarm_ids = [int(r["enter_alarm_id"]) for r in rows if r.get("enter_alarm_id") is not None]

    sample = rows[:20]
    before_sessions = [await _load_session_snapshot(db, int(r["id"])) for r in sample]
    before_alarms = [
        await _load_alarm_snapshot(db, int(r["enter_alarm_id"]))
        for r in sample
        if r.get("enter_alarm_id")
    ]

    r1 = await db.execute(
        text(
            "UPDATE rtu_alarm_session SET acked=1, acked_at=:now, acked_by=:by, ack_note=:note WHERE acked=0 AND id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"now": now, "by": body.acked_by, "note": body.ack_note, "ids": session_ids},
    )
    sessions_acked = int(getattr(r1, "rowcount", 0) or 0)

    alarms_acked = 0
    if alarm_ids:
        r2 = await db.execute(
            text(
                "UPDATE rtu_alarm_log SET acked=1, acked_at=:now, acked_by=:by, ack_note=:note WHERE acked=0 AND id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)),
            {"now": now, "by": body.acked_by, "note": body.ack_note, "ids": alarm_ids},
        )
        alarms_acked = int(getattr(r2, "rowcount", 0) or 0)

    after_sessions = [await _load_session_snapshot(db, int(r["id"])) for r in sample]
    after_alarms = [
        await _load_alarm_snapshot(db, int(r["enter_alarm_id"]))
        for r in sample
        if r.get("enter_alarm_id")
    ]

    await _insert_ack_audit(
        db,
        rtu_id=rtu_id,
        action="ACK_ACTIVE",
        actor=body.acked_by,
        note=body.ack_note,
        target_type="BULK",
        target_id=None,
        alarms_acked=alarms_acked,
        sessions_acked=sessions_acked,
        client_host=request.client.host if request.client else None,
        snapshot_before={
            "total": len(rows),
            "sessions": [x for x in before_sessions if x],
            "alarms": [x for x in before_alarms if x],
        },
        snapshot_after={
            "sessions": [x for x in after_sessions if x],
            "alarms": [x for x in after_alarms if x],
        },
    )
    await db.commit()
    return AckOut(ok=True, alarms_acked=alarms_acked, sessions_acked=sessions_acked)


# -------------------------
# Connection Control Endpoints
# -------------------------
class ConnectIn(BaseModel):
    port: str
    baudrate: int = 9600
    # 필요한 경우 unit_id 등 추가 가능


class ConnectionOut(BaseModel):
    ok: bool
    message: str


# 임시로 워커 매니저를 가져온다고 가정합니다.
from app.workers.manager import worker_manager


@router.post("/connect", response_model=ConnectionOut)
async def connect_rtu(rtu_id: int, body: ConnectIn):  # 🚀 [패치] rtu_id 파라미터 추가
    """프론트엔드 UI에서 통신 연결 버튼을 눌렀을 때 호출됨"""
    try:
        success = await worker_manager.apply_comm_settings(
            rtu_id=rtu_id, port=body.port, baudrate=body.baudrate
        )
        if success:
            return ConnectionOut(ok=True, message=f"[RTU {rtu_id}] {body.port} 연결 성공")
        else:
            return ConnectionOut(
                ok=False, message=f"[RTU {rtu_id}] {body.port} 연결 실패 (포트 점유 등 확인)"
            )
    except Exception as e:
        return ConnectionOut(ok=False, message=f"연결 중 오류 발생: {str(e)}")


@router.post("/disconnect", response_model=ConnectionOut)
async def disconnect_rtu(rtu_id: int):  # 🚀 [패치] rtu_id 파라미터 추가
    """프론트엔드 UI에서 통신 해제 버튼을 눌렀을 때 호출됨"""
    try:
        await worker_manager.disconnect_comm(rtu_id=rtu_id)
        return ConnectionOut(ok=True, message=f"[RTU {rtu_id}] 연결이 해제되었습니다.")
    except Exception as e:
        return ConnectionOut(ok=False, message=f"해제 중 오류 발생: {str(e)}")
