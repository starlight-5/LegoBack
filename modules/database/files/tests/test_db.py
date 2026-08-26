"""DB 연동 실제 동작 테스트 (database 모듈, SQL 변형)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.core.db as db_module
from src.core.db import apply, get_db, get_engine


def test_get_engine_reads_database_url_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    engine = get_engine()
    assert str(engine.url) == "sqlite:///:memory:"


def test_get_engine_falls_back_to_default_when_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    engine = get_engine()
    # str(engine.url)은 보안상 비밀번호를 ***로 가리므로, 실제 값 비교는 render_as_string으로 한다.
    assert engine.url.render_as_string(hide_password=False) == "postgresql://app:app@db:5432/app"


def test_get_db_yields_working_session_and_closes_it(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    gen = get_db()
    db = next(gen)
    assert isinstance(db, Session)
    assert db.execute(text("SELECT 1")).scalar() == 1

    closed = {"called": False}
    original_close = db.close

    def _spy_close():
        closed["called"] = True
        original_close()

    db.close = _spy_close
    next(gen, None)  # finally 블록(db.close()) 실행까지 제너레이터를 끝까지 돌림
    assert closed["called"]


def test_apply_runs_alembic_upgrade_head_on_startup(monkeypatch):
    calls = []
    monkeypatch.setattr(
        db_module.command, "upgrade",
        lambda cfg, revision: calls.append((cfg.config_file_name, revision)),
    )

    app = FastAPI()
    apply(app)
    with TestClient(app):
        pass  # 컨텍스트 진입 시 startup 이벤트가 실행된다

    assert len(calls) == 1
    config_file_name, revision = calls[0]
    assert config_file_name.endswith("alembic.ini")
    assert revision == "head"
