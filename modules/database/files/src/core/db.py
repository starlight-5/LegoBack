"""DB 연동 (database 모듈)."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def get_engine():
    # settings 모듈의 Settings는 APP_ENV만 선언하고 extra="ignore"라
    # DATABASE_URL은 get_settings()로 못 읽는다 (cors 모듈과 동일하게 os.getenv 직접 사용).
    url = os.getenv("DATABASE_URL", "postgresql://app:app@db:5432/app")
    return create_engine(url)


SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def get_db():
    """FastAPI 의존성: 요청마다 세션 열고 닫기."""
    SessionLocal.configure(bind=get_engine())
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
