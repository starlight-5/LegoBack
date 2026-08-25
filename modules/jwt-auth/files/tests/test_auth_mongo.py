"""회원가입·로그인·토큰 재발급 실제 동작 테스트 (jwt-auth 모듈, MongoDB 변형)."""
import asyncio

from jose import jwt

from conftest import client
from src.models.user import User
from src.routers.auth import ALGORITHM


def test_signup_returns_tokens():
    res = client.post("/auth/signup", json={"email": "a@b.c", "password": "pw12345"})
    assert res.status_code == 201
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]


async def _find_by_email(email: str) -> User:
    return await User.find_one(User.email == email)


def test_signup_hashes_password_not_plaintext():
    client.post("/auth/signup", json={"email": "hash@b.c", "password": "pw12345"})
    # User.find_one(...)는 코루틴이 아니라 별도의 쿼리 객체(FindOne)라, asyncio.run()에
    # 바로 넘기면 안 된다 — Python 3.14는 awaitable이면 알아서 감싸줘서 통과하지만,
    # 3.12 이하는 진짜 코루틴만 받아서 "a coroutine was expected"로 죽는다.
    # async def로 한 번 감싸서 진짜 코루틴을 만들어 넘겨야 버전에 상관없이 동작한다.
    user = asyncio.run(_find_by_email("hash@b.c"))
    assert user.hashed_password != "pw12345"
    assert user.hashed_password.startswith("$2b$")


def test_signup_duplicate_email_rejected():
    client.post("/auth/signup", json={"email": "dup@b.c", "password": "pw12345"})
    res = client.post("/auth/signup", json={"email": "dup@b.c", "password": "other-pw"})
    assert res.status_code == 409


def test_first_signup_becomes_admin():
    res = client.post("/auth/signup", json={"email": "first@b.c", "password": "pw12345"})
    payload = jwt.decode(res.json()["access_token"], "test-secret-key", algorithms=[ALGORITHM])
    assert payload["role"] == "ADMIN"


def test_second_signup_stays_user():
    client.post("/auth/signup", json={"email": "first2@b.c", "password": "pw12345"})
    res = client.post("/auth/signup", json={"email": "second2@b.c", "password": "pw12345"})
    payload = jwt.decode(res.json()["access_token"], "test-secret-key", algorithms=[ALGORITHM])
    assert payload["role"] == "USER"


def test_login_with_correct_password_succeeds():
    client.post("/auth/signup", json={"email": "login@b.c", "password": "pw12345"})
    res = client.post("/auth/login", json={"email": "login@b.c", "password": "pw12345"})
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_login_with_wrong_password_rejected():
    client.post("/auth/signup", json={"email": "login2@b.c", "password": "pw12345"})
    res = client.post("/auth/login", json={"email": "login2@b.c", "password": "wrong-pw"})
    assert res.status_code == 401


def test_login_with_unknown_email_rejected():
    res = client.post("/auth/login", json={"email": "nobody@b.c", "password": "pw12345"})
    assert res.status_code == 401


def test_refresh_issues_new_access_token():
    signup_res = client.post("/auth/signup", json={"email": "refresh@b.c", "password": "pw12345"})
    refresh_token = signup_res.json()["refresh_token"]

    res = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    access_token = res.json()["access_token"]

    payload = jwt.decode(access_token, "test-secret-key", algorithms=[ALGORITHM])
    assert payload["sub"] == "refresh@b.c"
    assert payload["type"] == "access"


def test_refresh_rejects_access_token():
    signup_res = client.post("/auth/signup", json={"email": "noaccess@b.c", "password": "pw12345"})
    access_token = signup_res.json()["access_token"]

    res = client.post("/auth/refresh", json={"refresh_token": access_token})
    assert res.status_code == 401


def test_refresh_rejects_garbage_token():
    res = client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert res.status_code == 401
