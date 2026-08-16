"""관리자 승격 엔드포인트(PATCH /admin/users/{email}/promote) 실제 동작 테스트 (rbac 모듈)."""
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db import Base, get_db
from src.main import app
from src.models.user import User
from src.routers.auth import ALGORITHM

SECRET = "test-secret-key"

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
    # get_db 오버라이드를 매 테스트 직전에 다시 지정한다 — jwt-auth의
    # test_auth.py도 같은 src.main.app에 자기 own DB로 오버라이드를 걸어두므로,
    # 모듈 최상단에서 한 번만 지정하면 나중에 임포트된 파일의 오버라이드가
    # 이 파일 테스트 실행 시점까지 남아있을 수 있다.
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _token(role: str, sub: str = "caller@b.c") -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "role": role, "type": "access", "iat": now, "exp": now + timedelta(minutes=30)}
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def _seed_user(email: str, role: str = "USER") -> None:
    db = TestingSessionLocal()
    db.add(User(email=email, hashed_password="x", role=role))
    db.commit()
    db.close()


def test_admin_can_promote_user():
    _seed_user("target@b.c")
    res = client.patch(
        "/admin/users/target@b.c/promote",
        headers={"Authorization": f"Bearer {_token('ADMIN')}"},
    )
    assert res.status_code == 200
    assert res.json() == {"email": "target@b.c", "role": "ADMIN"}


def test_non_admin_cannot_promote():
    _seed_user("target2@b.c")
    res = client.patch(
        "/admin/users/target2@b.c/promote",
        headers={"Authorization": f"Bearer {_token('USER')}"},
    )
    assert res.status_code == 403


def test_promote_unknown_email_returns_404():
    res = client.patch(
        "/admin/users/nobody@b.c/promote",
        headers={"Authorization": f"Bearer {_token('ADMIN')}"},
    )
    assert res.status_code == 404


def test_admin_can_demote_another_admin():
    _seed_user("admin1@b.c", role="ADMIN")
    _seed_user("admin2@b.c", role="ADMIN")
    res = client.patch(
        "/admin/users/admin2@b.c/demote",
        headers={"Authorization": f"Bearer {_token('ADMIN', sub='admin1@b.c')}"},
    )
    assert res.status_code == 200
    assert res.json() == {"email": "admin2@b.c", "role": "USER"}


def test_demoting_the_last_admin_is_rejected():
    _seed_user("onlyadmin@b.c", role="ADMIN")
    res = client.patch(
        "/admin/users/onlyadmin@b.c/demote",
        headers={"Authorization": f"Bearer {_token('ADMIN', sub='onlyadmin@b.c')}"},
    )
    assert res.status_code == 409


def test_non_admin_cannot_demote():
    _seed_user("target3@b.c", role="ADMIN")
    res = client.patch(
        "/admin/users/target3@b.c/demote",
        headers={"Authorization": f"Bearer {_token('USER')}"},
    )
    assert res.status_code == 403


def test_demote_unknown_email_returns_404():
    res = client.patch(
        "/admin/users/nobody@b.c/demote",
        headers={"Authorization": f"Bearer {_token('ADMIN')}"},
    )
    assert res.status_code == 404
