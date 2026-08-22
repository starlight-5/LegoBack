"""회원가입·로그인·토큰 재발급 (jwt-auth 모듈)."""
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.models.user import User

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _jwt_settings() -> tuple[str, int, int]:
    # settings 모듈의 Settings는 APP_ENV만 선언하고 extra="ignore"라
    # JWT_* 값은 get_settings()로 못 읽는다 (cors 모듈과 동일하게 os.getenv 직접 사용).
    secret = os.getenv("JWT_SECRET_KEY", "")
    access_minutes = int(os.getenv("JWT_ACCESS_MINUTES", "30"))
    refresh_minutes = int(os.getenv("JWT_REFRESH_MINUTES", "10080"))
    return secret, access_minutes, refresh_minutes


def _create_token(subject: str, role: str, token_type: str, secret: str, expires_minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def _issue_tokens(user: User) -> TokenResponse:
    secret, access_minutes, refresh_minutes = _jwt_settings()
    access_token = _create_token(user.email, user.role, "access", secret, access_minutes)
    refresh_token = _create_token(user.email, user.role, "refresh", secret, refresh_minutes)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


def decode_access_token(token: str) -> dict:
    """access 토큰을 검증하고 payload를 반환한다. rbac 모듈이 role 검사에 재사용."""
    secret, _, _ = _jwt_settings()
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="access 토큰이 아닙니다.")

    return payload


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.query(User).filter(User.email == body.email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 가입된 이메일입니다.")

    # 이 배포에 가입자가 아직 한 명도 없으면 첫 가입자를 ADMIN으로 만든다 (팀 결정사항, 2026-08-03).
    is_first_user = db.query(User).first() is None
    role = "ADMIN" if is_first_user else "USER"
    user = User(email=body.email, hashed_password=pwd_context.hash(body.password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)

    return _issue_tokens(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not pwd_context.verify(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    return _issue_tokens(user)


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(body: RefreshRequest) -> AccessTokenResponse:
    secret, access_minutes, _ = _jwt_settings()
    try:
        payload = jwt.decode(body.refresh_token, secret, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh 토큰이 아닙니다.")

    access_token = _create_token(payload["sub"], payload.get("role", "USER"), "access", secret, access_minutes)
    return AccessTokenResponse(access_token=access_token)

