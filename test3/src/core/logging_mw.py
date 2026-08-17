"""요청 로깅 (logging 모듈).

모든 HTTP 요청의 메서드, 경로, 상태 코드, 처리 시간을 기록한다.

환경 변수:
LOG_LEVEL: 로그 레벨. 기본값은 INFO.
DEBUG, INFO, WARNING, ERROR, CRITICAL 등을 사용할 수 있다.

등록:
manifest.yaml의 registrations에 선언된
`src.core.logging_mw.apply`를 엔진이 main.py에서 호출한다.
"""

import logging
import os
import time
from logging.handlers import TimedRotatingFileHandler

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


LOGGER_NAME = "app"

logger = logging.getLogger(LOGGER_NAME)


def _configure_logging() -> None:
    """환경 변수에 따라 애플리케이션 로깅을 설정한다."""

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()

    # 존재하지 않는 로그 레벨이 들어와도 애플리케이션이
    # 시작 단계에서 죽지 않도록 INFO를 기본값으로 사용한다.
    level = getattr(logging, level_name, logging.INFO)

    os.makedirs("logs", exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # 콘솔 출력
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # 일반 애플리케이션 로그
    file_handler = TimedRotatingFileHandler(
        filename="logs/app.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # logging 설정이 여러 번 실행될 경우
    # handler가 중복 등록되는 것을 방지한다.
    root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


async def log_requests(
    request: Request,
    call_next,
) -> Response:
    """HTTP 요청을 처리하고 요청 정보를 로그로 남긴다."""

    start = time.perf_counter()

    try:
        response = await call_next(request)

    except Exception:
        # 실제 예외 내용과 traceback은 exceptions.py에서 처리한다.
        # 여기서는 예외 로그를 중복 기록하지 않고 다시 전달한다.
        raise

    elapsed_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "%s %s → %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )

    return response


def apply(app: FastAPI) -> None:
    """FastAPI 애플리케이션에 logging 모듈을 등록한다."""

    _configure_logging()

    app.add_middleware(
        BaseHTTPMiddleware,
        dispatch=log_requests,
    )