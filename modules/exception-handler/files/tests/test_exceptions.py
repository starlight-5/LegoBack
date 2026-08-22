"""exception-handler 모듈의 예외 처리 검증."""

from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


# 모듈 파일의 실제 경로를 직접 로드한다.
MODULES = Path(__file__).parents[1] / "modules"
EXCEPTIONS = MODULES / "exception-handler" / "files" / "src" / "core"

sys.path.insert(0, str(EXCEPTIONS))

from exceptions import apply  # noqa: E402


def _make_app() -> FastAPI:
    """exception-handler가 등록된 테스트용 FastAPI 앱을 만든다."""

    app = FastAPI()
    apply(app)

    @app.get("/test/http-error")
    async def http_error():
        raise HTTPException(
            status_code=404,
            detail="테스트용 HTTP 예외입니다.",
        )

    @app.get("/test/validation")
    async def validation(value: int):
        return {"value": value}

    @app.get("/test/server-error")
    async def server_error():
        raise RuntimeError("테스트용 서버 예외입니다.")

    return app


def test_http_exception_handler():
    """HTTPException이 일관된 JSON 응답으로 변환되는지 검증."""

    client = TestClient(_make_app())

    response = client.get("/test/http-error")

    assert response.status_code == 404
    assert response.json() == {
        "error": "HTTP_ERROR",
        "message": "테스트용 HTTP 예외입니다.",
    }


def test_validation_exception_handler():
    """요청 데이터 검증 오류가 일관된 JSON 응답으로 변환되는지 검증."""

    client = TestClient(_make_app())

    response = client.get(
        "/test/validation",
        params={"value": "invalid"},
    )

    assert response.status_code == 422

    body = response.json()

    assert body["error"] == "VALIDATION_ERROR"
    assert body["message"] == "요청 데이터가 올바르지 않습니다."
    assert "details" in body


def test_unexpected_exception_handler(tmp_path, monkeypatch):
    """처리되지 않은 예외가 500 응답과 로그로 처리되는지 검증."""

    monkeypatch.chdir(tmp_path)

    client = TestClient(
        _make_app(),
        raise_server_exceptions=False,
    )

    response = client.get("/test/server-error")

    assert response.status_code == 500
    assert response.json() == {
        "error": "INTERNAL_SERVER_ERROR",
        "message": "서버 내부 오류가 발생했습니다.",
    }

    log_file = tmp_path / "logs" / "exception.log"

    assert log_file.exists()

    log_content = log_file.read_text(encoding="utf-8")

    assert "Unhandled exception: GET /test/server-error" in log_content
    assert "RuntimeError: 테스트용 서버 예외입니다." in log_content