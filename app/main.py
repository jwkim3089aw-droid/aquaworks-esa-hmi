# app/main.py
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.api.v1.telemetry import simulator_task
from app.core.config import Settings, get_settings
from app.db.session import init_db
from app.services.telemetry_store import get_store


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()
        s = get_settings()
        sim = None

        enable_sim = getattr(s, "ENABLE_SIMULATOR", True)
        interval = getattr(s, "SIM_INTERVAL_SEC", 1.0)
        if enable_sim:
            sim = asyncio.create_task(simulator_task(get_store(), interval))

        try:
            yield
        finally:
            if sim:
                sim.cancel()
                with contextlib.suppress(Exception):
                    await sim

    app = FastAPI(title="ESA_HMI", lifespan=lifespan)
    app.include_router(api_router)

    ss: Settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=getattr(ss, "CORS_ORIGINS", ["http://localhost:5173"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _root_sync() -> dict[str, str]:
        app_name: str = cast(str, getattr(ss, "APP_NAME", "ESA_HMI"))
        return {"status": "ok", "app": app_name}

    app.add_api_route("/", _root_sync, methods=["GET"], include_in_schema=False)
    return app


app = create_app()


# health 체크
@app.get("/health")
def healt():
    return {"status": "ok"}
