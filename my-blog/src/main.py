"""my-blog — fastapi-scaffold로 생성됨."""
from fastapi import FastAPI
from src.routers.auth import router as auth_router

app = FastAPI(title="my-blog")


@app.get("/health")
def health() -> dict:
    """서버 생존 확인용 엔드포인트."""
    return {"status": "ok"}

app.include_router(auth_router, prefix="/auth", tags=["auth"])
