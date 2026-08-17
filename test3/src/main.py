"""test3 — fastapi-scaffold로 생성됨."""
from fastapi import FastAPI
from src.core.logging_mw import apply as logging_mw_apply
from src.core.exceptions import apply as exceptions_apply

app = FastAPI(title="test3")

logging_mw_apply(app)
exceptions_apply(app)

@app.get("/health")
def health() -> dict:
    """서버 생존 확인용 엔드포인트."""
    return {"status": "ok"}

