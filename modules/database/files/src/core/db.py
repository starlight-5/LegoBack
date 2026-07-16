"""DB 연동 (database 모듈).

TODO(모듈 파트): Alembic 마이그레이션 셋업, Base 선언, 세션 의존성 정리.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.core.config import get_settings


class Base(DeclarativeBase):
    pass


def get_engine():
    return create_engine(get_settings().DATABASE_URL)


SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def get_db():
    """FastAPI 의존성: 요청마다 세션 열고 닫기."""
    SessionLocal.configure(bind=get_engine())
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
