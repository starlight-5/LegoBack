"""테스트 공통 설정 (jwt-auth 모듈이 제공, rbac 등 다른 모듈의 테스트도 같이 씀).

여러 모듈의 테스트 파일이 전부 같은 src.main.app을 대상으로 테스트하다 보니,
"실제 DATABASE_URL 없이도 검증 가능하도록 sqlite 메모리 DB로 get_db를
오버라이드"하는 설정을 각 테스트 파일마다 복사해두면 안 됐다(중복 코드).
pytest는 conftest.py 안의 autouse 픽스처를 같은 폴더의 모든 테스트 파일에
자동으로 적용해주므로, 여기 한 곳에서만 관리한다.
"""
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db import Base, get_db
from src.main import app

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_db():
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
