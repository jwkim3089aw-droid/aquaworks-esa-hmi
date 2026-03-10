# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, List


class Settings(BaseSettings):
    APP_NAME: str = "ESA_HMI"
    DEBUG: bool = True

    # ---- DB 설정 ----
    DB_URL: str = "sqlite+aiosqlite:///./.data/esa_hmi.db"
    DB_ECHO: bool = False

    # ---- UI 서버 설정 (NiceGUI) ----
    UI_HOST: str = "127.0.0.1"
    UI_PORT: int = 8090

    # ---- PLC(Modbus) 설정 ----
    PLC_HOST: str = "127.0.0.1"
    PLC_PORT: int = 5020
    PLC_DEVICE_ID: int = 1
    PLC_FRAMER: Literal["SOCKET", "TCP", "TLS", "RTU"] = "SOCKET"

    # CORS: pydantic-settings에선 env로 넣을 땐 JSON 문자열 필요
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    model_config = SettingsConfigDict(
        env_prefix="ESA_",
        env_file=".env",
        extra="ignore",
    )

    ENABLE_SIMULATION: bool = False
    SIM_INTERVAL_SEC: float = 1.0


def get_settings() -> Settings:
    return Settings()
