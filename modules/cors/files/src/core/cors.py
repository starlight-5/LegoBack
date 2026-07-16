"""CORS 설정 (cors 모듈).

사용법(임시): main.py 에서 `from src.core.cors import apply; apply(app)`
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def apply(app: FastAPI) -> None:
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(
        CORSMiddleware, allow_origins=origins,
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
