from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_signup_stub():
    res = client.post("/auth/signup", params={"email": "a@b.c", "password": "pw"})
    assert res.status_code == 200
