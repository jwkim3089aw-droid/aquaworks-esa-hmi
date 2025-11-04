# app/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "ESA_HMI"
    DEBUG: bool = True
    CORS_ORIGINS: list[str] = [
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

    ENABLE_SIMULATON: bool = True
    SIM_INTERVAL_SEC: float = 1.0


def get_settings() -> Settings:
    return Settings()
