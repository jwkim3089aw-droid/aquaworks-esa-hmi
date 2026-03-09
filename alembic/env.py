import asyncio
from logging.config import fileConfig
import os
import sys

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ----------------------------------------------------------------------
# [1] 프로젝트 경로 설정 (app 모듈을 찾기 위해 필수)
# ----------------------------------------------------------------------
sys.path.insert(0, os.getcwd())

# ----------------------------------------------------------------------
# [2] 프로젝트 설정 및 모델 임포트
# ----------------------------------------------------------------------
from app.core.config import get_settings
from app.core.db import Base  # app/core/db.py의 Base 사용

# ★ 중요: Alembic이 변경사항을 감지하려면 모든 모델을 여기서 import 해야 합니다.
# 파일 리스트에 있던 기존 모델들과 새로 만든 rtu 모델을 가져옵니다.
from app.models import command
from app.models import settings
from app.models import telemetry
from app.models import ui_theme
from app.models import rtu  # 이번에 추가한 RTU 모델

# ----------------------------------------------------------------------
# [3] Alembic Config 설정
# ----------------------------------------------------------------------
config = context.config

# 로깅 설정 적용
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# [4] DB URL 설정 덮어쓰기
# alembic.ini의 sqlalchemy.url 대신 app.core.config의 설정을 사용합니다.
app_settings = get_settings()
config.set_main_option("sqlalchemy.url", app_settings.DB_URL)

# [5] 메타데이터 연결 (Auto Generate를 위해 필수)
target_metadata = Base.metadata

# ----------------------------------------------------------------------
# 마이그레이션 실행 함수들
# ----------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite에서 컬럼 변경/삭제 등을 지원하기 위해 배치 모드 활성화 권장
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite에서 컬럼 변경/삭제 등을 지원하기 위해 배치 모드 활성화 권장
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
