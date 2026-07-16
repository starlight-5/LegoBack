"""통일 에러 응답 (exception-handler 모듈).

TODO(모듈 파트): main.py 자동 연결은 manifest registrations 필드 확정 후.
그 전까지 사용법: src/main.py 에서 `from src.core.exceptions import register; register(app)`
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def register(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL", "message": "서버 오류가 발생했습니다."},
        })
