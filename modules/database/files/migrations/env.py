"""Alembic 마이그레이션 환경 설정 (database 모듈).

DB 접속 주소는 alembic.ini에 적지 않고 여기서 DATABASE_URL 환경 변수로
읽는다 — db.py의 get_engine()과 동일한 방식으로, 주소를 한 곳에서만
관리하기 위함.

모델은 여러 모듈(jwt-auth 등)이 각자 src/models/ 아래에 나눠서 추가하므로,
이 파일이 특정 모델을 직접 import하지 않는다. 대신 src/models/ 폴더 안의
모든 .py 파일을 찾아서 import해 Base.metadata에 등록시킨다 — 그래야
autogenerate가 어떤 모듈의 모델이 설치됐는지 몰라도 전부 인식한다.
"""
import importlib
import logging
import os
import pkgutil
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.core.db import Base

MODELS_DIR = Path(__file__).resolve().parents[1] / "src" / "models"
if MODELS_DIR.is_dir():
    for _, module_name, _ in pkgutil.iter_modules([str(MODELS_DIR)]):
        importlib.import_module(f"src.models.{module_name}")

config = context.config

if config.config_file_name is not None:
    # fileConfig()는 alembic.ini의 [logger_root]를 그대로 적용해 root 로거의
    # 핸들러를 갈아치운다 — disable_existing_loggers=False로 막아도 root처럼
    # [loggers]에 명시된 로거는 예외 없이 재구성된다. db.apply()가 서버 기동
    # 시(startup 이벤트) 이 env.py를 거치므로, 그대로 두면 logging/
    # exception-handler 모듈이 이미 붙여둔 app.log 핸들러가 사라져서 실제
    # 요청에서는 로그가 하나도 안 남는다. root 핸들러를 잠깐 저장했다가
    # fileConfig() 직후 그대로 복원해 이 문제를 피한다.
    _root_logger = logging.getLogger()
    _root_handlers = _root_logger.handlers[:]
    _root_level = _root_logger.level
    fileConfig(config.config_file_name, disable_existing_loggers=False)
    _root_logger.handlers[:] = _root_handlers
    _root_logger.setLevel(_root_level)

config.set_main_option(
    "sqlalchemy.url",
    os.getenv("DATABASE_URL", "postgresql://app:app@db:5432/app"),
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """DB에 접속하지 않고 SQL문만 생성 (alembic upgrade --sql 등에 사용)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """DB에 실제로 접속해서 마이그레이션 실행 (일반적인 사용 방식)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
