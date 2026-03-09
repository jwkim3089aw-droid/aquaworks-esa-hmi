# app/models/rtu.py
from __future__ import annotations

import time
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, Text, Boolean
from app.core.db import Base  # app/core/db.py의 Base 사용


# 1. App Settings (Key-Value)
class AppSettings(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(Float)


# 2. RTU Health
class RtuHealth(Base):
    __tablename__ = "rtu_health"

    id = Column(Integer, primary_key=True, default=1)
    updated_at = Column(Float)
    last_success_at = Column(Float)
    connected = Column(Integer, default=0)  # Boolean 대신 Integer (0/1) 사용 호환성
    port = Column(String, nullable=True)
    baudrate = Column(Integer, nullable=True)
    unit_id = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    consecutive_failures = Column(Integer, default=0)
    last_read_ms = Column(Float, nullable=True)
    last_write_ms = Column(Float, nullable=True)
    write_q_size = Column(Integer, nullable=True)
    ingest_q_size = Column(Integer, nullable=True)
    db_q_size = Column(Integer, nullable=True)
    read_ok_rate_60s = Column(Float, nullable=True)
    write_ok_rate_60s = Column(Float, nullable=True)


# 3. Alarm Log
class RtuAlarmLog(Base):
    __tablename__ = "rtu_alarm_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(Float, nullable=False)
    event_type = Column(String, nullable=False)
    severity = Column(Integer, nullable=False)
    message = Column(Text, nullable=False)
    port = Column(String, nullable=True)
    baudrate = Column(Integer, nullable=True)
    unit_id = Column(Integer, nullable=True)
    age_sec = Column(Float, nullable=True)
    stale_threshold_sec = Column(Float, nullable=True)
    last_error = Column(Text, nullable=True)
    consecutive_failures = Column(Integer, nullable=True)

    # ACK Columns
    acked = Column(Integer, default=0)
    acked_at = Column(Float, nullable=True)
    acked_by = Column(String, nullable=True)
    ack_note = Column(Text, nullable=True)


# 4. Alarm Session
class RtuAlarmSession(Base):
    __tablename__ = "rtu_alarm_session"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, nullable=False)
    start_ts = Column(Float, nullable=False)
    end_ts = Column(Float, nullable=True)
    duration_sec = Column(Float, nullable=True)
    enter_alarm_id = Column(Integer, nullable=True)
    exit_alarm_id = Column(Integer, nullable=True)

    # ACK Columns
    acked = Column(Integer, default=0)
    acked_at = Column(Float, nullable=True)
    acked_by = Column(String, nullable=True)
    ack_note = Column(Text, nullable=True)

    port = Column(String, nullable=True)
    baudrate = Column(Integer, nullable=True)
    unit_id = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    consecutive_failures = Column(Integer, nullable=True)


# 5. Write Command Queue
class RtuWriteCmd(Base):
    __tablename__ = "rtu_write_cmd"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(Float, nullable=False)
    expires_at = Column(Float, nullable=False)
    requested_by = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    addr = Column(Integer, nullable=False)
    value = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # PENDING, RUNNING, DONE...
    started_at = Column(Float, nullable=True)
    executed_at = Column(Float, nullable=True)
    latency_ms = Column(Float, nullable=True)
    ok = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)


# 6. ACK Audit (감사 로그)
class RtuAckAudit(Base):
    __tablename__ = "rtu_ack_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(Float, nullable=False)
    action = Column(String, nullable=False)
    actor = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    target_type = Column(String, nullable=True)
    target_id = Column(Integer, nullable=True)
    alarms_acked = Column(Integer, default=0)
    sessions_acked = Column(Integer, default=0)
    client_host = Column(String, nullable=True)

    # Snapshots (JSON Text)
    snapshot_before = Column(Text, nullable=True)
    snapshot_after = Column(Text, nullable=True)
