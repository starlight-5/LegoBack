"""JWT 인증 라우터 (jwt-auth 모듈).

TODO(모듈 파트): 실제 로직 구현 — 비밀번호 해싱(passlib), 토큰 발급(jose),
DB 저장(database 모듈 연동). 현재는 스텁으로 API 형태만 제공한다.
"""
from fastapi import APIRouter

router = APIRouter()


@router.post("/signup")
def signup(email: str, password: str) -> dict:
    # TODO: 해싱 후 User 저장
    return {"todo": "signup", "email": email}


@router.post("/login")
def login(email: str, password: str) -> dict:
    # TODO: 검증 후 access/refresh 발급
    return {"todo": "login"}


@router.post("/refresh")
def refresh(refresh_token: str) -> dict:
    # TODO: refresh 검증 후 access 재발급
    return {"todo": "refresh"}
