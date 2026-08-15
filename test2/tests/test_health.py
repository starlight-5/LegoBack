"""기본 /health 테스트 — 앱이 임포트되고 라우팅이 동작함을 검증한다."""
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
