"""통일 에러 응답 (exception-handler 모듈).

어떤 예외가 나도 같은 형식의 에러 JSON으로 응답한다.
등록: manifest의 registrations에 선언된 apply(app)를 엔진이 main.py에서 호출한다.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def apply(app: FastAPI) -> None:
    """exception-handler 모듈 등록 함수: 통일 에러 응답 핸들러를 등록한다."""
    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL", "message": "서버 오류가 발생했습니다."},
        })
