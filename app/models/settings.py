# app/models/settings.py
from __future__ import annotations
import enum
from sqlalchemy import Integer, String, Boolean, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base
from pydantic import BaseModel  # [추가] 데이터 구조 정의용


# ----------------------------------------------------------------
# Enums
# ----------------------------------------------------------------
class BackendType(str, enum.Enum):
    MODBUS = "modbus"
    OPCUA = "opcua"


# ----------------------------------------------------------------
# Database Models (SQLAlchemy)
# ----------------------------------------------------------------
class ConnectionConfig(Base):
    __tablename__ = "connection_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    backend_type: Mapped[BackendType] = mapped_column(
        SAEnum(BackendType), default=BackendType.MODBUS
    )

    host: Mapped[str] = mapped_column(String, default="127.0.0.1")
    port: Mapped[int] = mapped_column(Integer, default=5020)
    unit_id: Mapped[int] = mapped_column(Integer, default=1)
    namespace_uri: Mapped[str | None] = mapped_column(
        String, default="http://esa-hmi.com", nullable=True
    )
    use_simulator: Mapped[bool] = mapped_column(Boolean, default=True)


# ----------------------------------------------------------------
# [추가] Data Schemas (Pydantic)
# UI에서 개별 소스 설정을 다룰 때 사용하는 클래스들입니다.
# ----------------------------------------------------------------
class ModbusSource(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 502
    unit_id: int = 1


class OpcUaSource(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 4840
    ns: str = "ns=2;s=Demo"
