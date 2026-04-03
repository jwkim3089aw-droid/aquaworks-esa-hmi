# app/core/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, List

# 1. 기준 경로 설정 (app/core/config.py 기준 3단계 위 -> code/ 디렉토리)
BASE_DIR = Path(__file__).resolve().parents[2]

# 2. 메인 데이터 및 로그 경로
DATA_DIR = BASE_DIR / ".data"
LOG_DIR = BASE_DIR / ".logs"


class Settings(BaseSettings):
    APP_NAME: str = "ESA_HMI"
    DEBUG: bool = True

    # ---- 📂 경로 및 디렉토리 설정 (pathlib 노출) ----
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = DATA_DIR
    LOG_DIR: Path = LOG_DIR

    # 시뮬레이터와 동일한 로그 격리 아키텍처 적용
    SYS_LOG_DIR: Path = LOG_DIR / "sys_resources"
    APP_LOG_DIR: Path = LOG_DIR / "app_events"
    AI_LOG_DIR: Path = LOG_DIR / "ai_agents"
    TELEMETRY_LOG_DIR: Path = LOG_DIR / "telemetry"

    # ---- 🗄️ DB 설정 ----
    # pathlib을 이용해 절대 경로로 주입 (실행 위치에 구애받지 않음)
    DB_URL: str = f"sqlite+aiosqlite:///{DATA_DIR.as_posix()}/esa_hmi.db"
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
    settings = Settings()

    # 3. 디렉토리 자동 생성 (시뮬레이터에서 검증된 멱등성 보장 로직)
    # get_settings()가 호출되는 순간 앱에 필요한 모든 폴더 구조가 준비됩니다.
    for path in [
        settings.DATA_DIR,
        settings.SYS_LOG_DIR,
        settings.APP_LOG_DIR,
        settings.AI_LOG_DIR,
        settings.TELEMETRY_LOG_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    return settings
