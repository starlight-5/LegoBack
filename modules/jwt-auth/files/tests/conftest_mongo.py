"""테스트 공통 설정 (jwt-auth 모듈이 제공, rbac 등 다른 모듈의 테스트도 같이 씀, MongoDB 변형).

실제 MongoDB 없이도 검증 가능하도록, get_db 의존성을 mongomock의 가짜 클라이언트로
초기화하는 버전으로 오버라이드한다. SQL 쪽 conftest.py와 목적은 같다 — 여러 모듈의
테스트 파일이 이 설정을 각자 복사해서 갖고 있지 않도록 여기 한 곳에서 관리한다.
"""
import asyncio
import os

# setdefault가 아니라 무조건 덮어쓰기: 도커 컨테이너 안에서 pytest를 돌리면 .env의
# 실제 JWT_SECRET_KEY가 이미 환경변수에 들어가 있어서 setdefault는 손도 못 대고,
# 그러면 이 값(=서버가 서명에 씀)과 아래 테스트들이 기대하는 고정값이 어긋나 죽는다.
os.environ["JWT_SECRET_KEY"] = "test-secret-key"

import pytest
from beanie import init_beanie
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from src.core.db import get_db
from src.main import app
from src.models.user import User

_mock_client = AsyncMongoMockClient()


async def _override_get_db() -> None:
    await init_beanie(database=_mock_client["test"], document_models=[User])


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_db():
    # get_db는 FastAPI 의존성이라 HTTP 요청이 들어와야 실행되는데, 일부 테스트는
    # HTTP 요청 없이 바로 User.insert()부터 호출해서(_seed_user) Beanie가 아직
    # 초기화되기 전에 DB 작업을 시도해 에러가 난다. 그래서 매 테스트 시작 전에
    # 미리 한 번 초기화해둔다.
    asyncio.run(_override_get_db())
    yield
    asyncio.run(User.delete_all())
