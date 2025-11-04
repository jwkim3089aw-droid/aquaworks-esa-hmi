# app/api/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.commands.air import router as air_router
from app.api.v1.commands.pump import router as pump_router
from app.api.v1.commands.router import router as commands_router
from app.api.v1.telemetry import router as telemetry_router

api_router = APIRouter()
api_router.include_router(telemetry_router)
api_router.include_router(commands_router)
api_router.include_router(air_router)
api_router.include_router(pump_router)
