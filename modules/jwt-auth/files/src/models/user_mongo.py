"""회원 정보 모델 (jwt-auth 모듈, MongoDB/Beanie 변형)."""
from typing import Annotated

from beanie import Document, Indexed
from pydantic import EmailStr


class User(Document):
    email: Annotated[EmailStr, Indexed(unique=True)]
    hashed_password: str
    role: str = "USER"

    class Settings:
        name = "users"
