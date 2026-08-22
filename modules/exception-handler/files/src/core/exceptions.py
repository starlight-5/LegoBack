"""예외 처리 (exceptions 모듈).

FastAPI에서 발생하는 예외를 일관된 JSON 응답으로 변환한다.

처리:
- HTTPException: FastAPI의 HTTP 예외
- RequestValidationError: 요청 데이터 검증 오류
- Exception: 처리되지 않은 서버 예외

처리되지 않은 서버 예외는 exception.log에 traceback을 기록하고,
클라이언트에는 내부 오류 정보를 노출하지 않는다.

등록:
manifest.yaml의 registrations에 선언된
`src.core.exceptions.apply`를 엔진이 호출한다.
"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


LOGGER_NAME = "app.exceptions"

logger = logging.getLogger(LOGGER_NAME)


def _configure_exception_logging() -> None:
    """예외 로그를 별도 파일에 기록하도록 설정한다."""

    os.makedirs("logs", exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    exception_handler = TimedRotatingFileHandler(
        filename="logs/exception.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )

    exception_handler.setFormatter(formatter)

    logger.setLevel(logging.ERROR)

    # apply()가 여러 번 호출되어도 handler가 중복 등록되지 않도록 한다.
    logger.handlers.clear()

    logger.addHandler(exception_handler)

    # app logger로 전달되어 app.log에 중복 기록되는 것을 방지한다.
    logger.propagate = False


async def handle_http_exception(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """HTTPException을 일관된 JSON 응답으로 변환한다."""

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_ERROR",
            "message": exc.detail,
        },
    )


async def handle_validation_exception(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """요청 데이터 검증 오류를 일관된 JSON 응답으로 변환한다."""

    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "요청 데이터가 올바르지 않습니다.",
            "details": exc.errors(),
        },
    )


async def handle_unexpected_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """처리되지 않은 예외를 기록하고 500 응답을 반환한다."""

    logger.exception(
        "Unhandled exception: %s %s",
        request.method,
        request.url.path,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "서버 내부 오류가 발생했습니다.",
        },
    )


def apply(app: FastAPI) -> None:
    """FastAPI 애플리케이션에 exception handler를 등록한다."""

    _configure_exception_logging()

    app.add_exception_handler(
        HTTPException,
        handle_http_exception,
    )

    app.add_exception_handler(
        RequestValidationError,
        handle_validation_exception,
    )

    app.add_exception_handler(
        Exception,
        handle_unexpected_exception,
    )