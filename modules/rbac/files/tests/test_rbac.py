"""역할 기반 접근 제어(require_role) 실제 동작 테스트 (rbac 모듈)."""
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from src.core.rbac import require_role
from src.routers.auth import ALGORITHM

SECRET = "test-secret-key"

app = FastAPI()


@app.get("/admin-only", dependencies=[require_role("ADMIN")])
def admin_only() -> dict:
    return {"ok": True}


client = TestClient(app)


def _make_token(role: str, token_type: str = "access") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "user@test.com",
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def test_missing_token_rejected():
    res = client.get("/admin-only")
    assert res.status_code == 401


def test_wrong_role_rejected():
    token = _make_token("USER")
    res = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_correct_role_allowed():
    token = _make_token("ADMIN")
    res = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_refresh_token_rejected():
    token = _make_token("ADMIN", token_type="refresh")
    res = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_garbage_token_rejected():
    res = client.get("/admin-only", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401
