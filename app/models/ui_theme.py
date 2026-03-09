# app/models/ui_theme.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class UiTheme(Base):
    __tablename__ = "ui_theme"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    hud_accent_rgb: Mapped[str] = mapped_column(String(32), nullable=False, default="6,182,212")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
