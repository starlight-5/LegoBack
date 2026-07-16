"""User 모델 스텁 (jwt-auth 모듈). TODO: database 모듈의 Base와 연동."""
from dataclasses import dataclass


@dataclass
class User:
    email: str
    hashed_password: str
    role: str = "USER"
