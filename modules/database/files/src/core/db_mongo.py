"""DB 연동 (database 모듈, MongoDB/Motor+Beanie 변형).

SQL 변형(db.py)과 이름을 맞추려고 함수 이름은 get_db로 같지만 하는 일은
다르다 — 세션을 만들어 돌려주는 게 아니라 "Beanie가 아직 초기화 안 됐으면
지금 한 번만 초기화한다"는 역할만 한다. Document 모델들은 세션 없이
클래스 메서드(User.find_one() 등)로 바로 DB에 접근하는 방식이라, 매 요청마다
뭔가를 만들어 돌려줄 필요가 없다.
"""
import importlib
import os
import pkgutil
from pathlib import Path

from beanie import Document, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"

_initialized = False


def _document_models() -> list[type[Document]]:
    """src/models/ 아래 모든 Beanie Document 모델을 찾아서 반환한다.

    jwt-auth가 어떤 모델을 추가했는지 이 파일은 몰라도 되도록, 폴더를
    스캔해 자동으로 찾는다 (alembic의 env.py와 같은 방식).
    """
    models: list[type[Document]] = []
    if MODELS_DIR.is_dir():
        for _, module_name, _ in pkgutil.iter_modules([str(MODELS_DIR)]):
            module = importlib.import_module(f"src.models.{module_name}")
            for value in vars(module).values():
                if isinstance(value, type) and issubclass(value, Document) and value is not Document:
                    models.append(value)
    return models


async def get_db() -> None:
    """FastAPI 의존성: 요청마다 호출되지만 실제 초기화는 최초 1번만 한다."""
    global _initialized
    if _initialized:
        return

    url = os.getenv("MONGO_URL", "mongodb://app:app@mongo:27017/app?authSource=admin")
    client = AsyncIOMotorClient(url)
    await init_beanie(database=client.get_default_database(), document_models=_document_models())
    _initialized = True


def apply(app) -> None:
    """main.py에서 app 생성 직후 호출됨.

    SQL 변형(db.py)의 apply()는 마이그레이션을 미리 실행하는 역할이고, Mongo는
    마이그레이션이 없으니 그 자리에서 할 일이 없다. 대신 원래 get_db()가 "첫 요청이
    올 때"까지 미루던 Beanie 초기화를, 서버가 뜨는 시점에 미리 해둔다 — 그래야
    첫 요청을 받은 사용자만 초기화 지연을 떠안는 일이 없다.
    """
    @app.on_event("startup")
    async def _init_beanie() -> None:
        await get_db()
