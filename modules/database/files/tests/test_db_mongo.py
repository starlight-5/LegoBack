"""DB 연동 실제 동작 테스트 (database 모듈, MongoDB 변형)."""
import asyncio
import shutil
import sys
from pathlib import Path

from beanie import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import src.core.db as db_module
from src.core.db import apply, get_db

MODELS_DIR = Path("src/models")


def test_document_models_finds_beanie_documents():
    """src/models/ 아래에 실제로 파일을 하나 만들어서, 스캔 로직이 진짜로 찾아내는지 확인한다."""
    is_new_dir = not MODELS_DIR.is_dir()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    init_file = MODELS_DIR / "__init__.py"
    init_is_new = not init_file.exists()
    if init_is_new:
        init_file.touch()
    temp_model = MODELS_DIR / "_temp_widget_for_test.py"
    temp_model.write_text(
        "from beanie import Document\n\n\nclass Widget(Document):\n    name: str\n",
        encoding="utf-8",
    )
    sys.modules.pop("src.models._temp_widget_for_test", None)
    try:
        found = db_module._document_models()
        assert any(m.__name__ == "Widget" for m in found)
        assert all(issubclass(m, Document) for m in found)
    finally:
        temp_model.unlink()
        sys.modules.pop("src.models._temp_widget_for_test", None)
        pycache = MODELS_DIR / "__pycache__"
        if pycache.is_dir():
            shutil.rmtree(pycache)  # import 과정에서 생기는 바이트코드 캐시 — 없애야 폴더가 진짜로 비어 rmdir이 된다
        if init_is_new:
            init_file.unlink()
        if is_new_dir:
            MODELS_DIR.rmdir()


def test_get_db_initializes_beanie_only_once(monkeypatch):
    monkeypatch.setattr(db_module, "_initialized", False)
    monkeypatch.setattr(db_module, "AsyncIOMotorClient", AsyncMongoMockClient)

    init_calls = []

    async def _fake_init_beanie(**kwargs):
        init_calls.append(kwargs)

    monkeypatch.setattr(db_module, "init_beanie", _fake_init_beanie)

    asyncio.run(get_db())
    asyncio.run(get_db())  # 두 번째 호출은 이미 초기화됐으니 아무 일도 안 일어나야 한다

    assert len(init_calls) == 1
    # 이 프로젝트에 다른 모듈(jwt-auth 등)이 함께 선택됐는지에 따라 실제 모델 개수는
    # 달라질 수 있으므로, "한 번만 호출됐고 리스트를 넘겼다"만 확인한다.
    assert isinstance(init_calls[0]["document_models"], list)


def test_get_db_reads_mongo_url_env(monkeypatch):
    monkeypatch.setattr(db_module, "_initialized", False)
    monkeypatch.setenv(
        "MONGO_URL", "mongodb://app:app@mongo:27017/customdb?authSource=admin",
    )

    seen = {}

    class _SpyClient(AsyncMongoMockClient):
        def __init__(self, url):
            seen["url"] = url
            super().__init__(url)

    monkeypatch.setattr(db_module, "AsyncIOMotorClient", _SpyClient)

    async def _fake_init_beanie(**kwargs):
        pass

    monkeypatch.setattr(db_module, "init_beanie", _fake_init_beanie)

    asyncio.run(get_db())
    assert seen["url"] == "mongodb://app:app@mongo:27017/customdb?authSource=admin"


def test_apply_calls_get_db_on_startup(monkeypatch):
    """서버가 뜰 때(요청 오기 전) get_db()가 이미 호출돼 있어야 한다.

    get_db() 내부(실제 Beanie 초기화)까지 mongomock으로 실제 돌리면, mongomock이
    아직 지원 안 하는 명령(buildInfo)을 beanie가 호출해서 여기서만 깨진다 — 실제
    MongoDB 서버에서는 없는 문제라 get_db() 자체는 이미 다른 테스트에서 검증했다.
    여기서는 "apply()가 startup 시점에 get_db()를 부르는지"만 확인한다.
    """
    calls = []

    async def _fake_get_db():
        calls.append(True)

    monkeypatch.setattr(db_module, "get_db", _fake_get_db)

    app = FastAPI()
    apply(app)
    assert calls == []  # apply()를 부르는 시점엔 아직 호출 전

    with TestClient(app):
        pass  # 컨텍스트 진입 시 startup 이벤트가 실행된다

    assert calls == [True]
