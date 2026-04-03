# app/main.py
from __future__ import annotations

import os
import sys
import logging
import asyncio
import contextlib
from contextlib import asynccontextmanager
from typing import cast
from logging.handlers import TimedRotatingFileHandler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.api.v1.telemetry import simulator_task
from app.core.config import Settings, get_settings
from app.db.session import init_db
from app.services.telemetry_store import get_store
from app.workers.sys_monitor import run_sys_monitor

settings = get_settings()

# ---------------------------------------------------------
# 📡 Telemetry 중앙 집중 로깅 (정석 아키텍처)
# ---------------------------------------------------------
telemetry_logger = logging.getLogger("telemetry")
telemetry_logger.setLevel(logging.INFO)
telemetry_logger.propagate = False  # 상위 루트 로거로의 중복 전파 방지

if not telemetry_logger.handlers:
    formatter = logging.Formatter("%(asctime)s - [%(name)s] - %(levelname)s - %(message)s")

    file_handler = TimedRotatingFileHandler(
        filename=settings.TELEMETRY_LOG_DIR / "comm.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    telemetry_logger.addHandler(file_handler)

    if os.environ.get("ESA_DEV") == "1":
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        telemetry_logger.addHandler(console_handler)


# ---------------------------------------------------------
# 🚀 FastAPI 애플리케이션 팩토리
# ---------------------------------------------------------
def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()

        sim_task = None
        sys_monitor_task = None

        enable_sim = getattr(settings, "ENABLE_SIMULATION", True)
        interval = getattr(settings, "SIM_INTERVAL_SEC", 1.0)

        if enable_sim:
            sim_task = asyncio.create_task(simulator_task(get_store(), interval))

        sys_monitor_task = asyncio.create_task(run_sys_monitor())

        try:
            yield
        finally:
            if sim_task:
                sim_task.cancel()
                with contextlib.suppress(Exception):
                    await sim_task

            if sys_monitor_task:
                sys_monitor_task.cancel()
                with contextlib.suppress(Exception):
                    await sys_monitor_task

    app = FastAPI(title=getattr(settings, "APP_NAME", "ESA_HMI"), lifespan=lifespan)
    app.include_router(api_router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=getattr(settings, "CORS_ORIGINS", ["http://localhost:5173"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _root_sync() -> dict[str, str]:
        return {"status": "ok", "app": getattr(settings, "APP_NAME", "ESA_HMI")}

    app.add_api_route("/", _root_sync, methods=["GET"], include_in_schema=False)
    return app


app = create_app()


@app.get("/health")
def health():
    return {"status": "ok"}
