"""DB 연동 (database 모듈)."""
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
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


def apply(app) -> None:
    """main.py에서 app 생성 직후 호출됨.

    서버가 시작될 때, 아직 DB에 적용 안 된 마이그레이션 파일이 있으면
    자동으로 적용한다(`alembic upgrade head`와 동일한 동작). 마이그레이션
    파일 자체를 새로 만드는 것(`alembic revision --autogenerate`)은 모델이
    바뀔 때마다 사람이 내용을 확인하며 해야 하지만, 이미 만들어져 검토까지
    끝난 파일을 적용하는 건 안전하므로 이 부분만 자동화했다.

    주의: migrations/env.py가 alembic.ini를 읽을 때 logging.config.fileConfig()를
    호출하는데, 이게 root 로거 핸들러를 alembic.ini의 [logger_root] 설정으로
    갈아치운다. 그대로 두면 이 startup 이벤트가 실행되는 순간 logging/
    exception-handler 모듈이 이미 붙여둔 app.log 핸들러가 사라져서, 서버가 뜬
    뒤 실제 요청에서는 로그가 하나도 안 남는 버그가 생긴다. env.py가 fileConfig()
    호출 전후로 root 핸들러를 저장·복원하는 이유가 이거다.
    """
    @app.on_event("startup")
    def _run_migrations() -> None:
        alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
        cfg = Config(str(alembic_ini))
        command.upgrade(cfg, "head")
