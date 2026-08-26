"""[5.1] 요청 로깅 미들웨어 테스트."""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


MODULE_FILES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_FILES))

from src.core.logging_mw import apply


def _create_test_app() -> FastAPI:
    """logging middleware가 등록된 테스트용 FastAPI 앱을 생성한다."""

    app = FastAPI()

    apply(app)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "ok"}

    return app


def test_request_logging():
    """HTTP 요청의 메서드, 경로, 상태 코드, 처리 시간이 로그에 기록되는지 확인한다."""

    app = _create_test_app()
    client = TestClient(app)

    records = []

    class TestHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = TestHandler()

    logger = logging.getLogger("app")
    logger.addHandler(handler)

    try:
        response = client.get("/test")
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 200

    messages = [
        record.getMessage()
        for record in records
    ]

    assert any("GET /test → 200" in message for message in messages)
    assert any("ms" in message for message in messages)


def test_request_logging_records_404():
    """존재하지 않는 요청의 404 상태 코드가 로그에 기록되는지 확인한다."""

    app = _create_test_app()
    client = TestClient(app)

    records = []

    class TestHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = TestHandler()

    logger = logging.getLogger("app")
    logger.addHandler(handler)

    try:
        response = client.get("/does-not-exist")
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 404

    messages = [
        record.getMessage()
        for record in records
    ]

    assert any(
        "GET /does-not-exist → 404" in message
        for message in messages
    )