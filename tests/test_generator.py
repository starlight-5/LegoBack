"""[2.3~2.5] 생성 검증: 최소 뼈대 · 배달 · 결정적 출력."""
from pathlib import Path

import pytest

from scaffold.engine.errors import DuplicateFileError
from scaffold.engine.generator import copy_module_files, generate, merge_packages
from scaffold.engine.loader import load_manifests
from scaffold.engine.manifest import FileMapping, ModuleManifest
from scaffold.engine.resolver import collect_env, filter_manifests, resolve

MODULES = Path(__file__).parents[1] / "modules"


def _make(tmp_path: Path, selected: list[str], name="demo") -> Path:
    m = load_manifests(MODULES)
    ordered = resolve(selected, m) if selected else []
    filtered = filter_manifests(m, {"db_type": "postgresql"})
    out = tmp_path / name
    generate(out, name, ordered, filtered, MODULES, collect_env(ordered, filtered))
    return out


def test_bare_skeleton(tmp_path):
    """[2.3.1] 완료 기준: 모듈 0개여도 /health 앱과 기본 테스트가 존재."""
    out = _make(tmp_path, [])
    main = (out / "src" / "main.py").read_text(encoding="utf-8")
    assert "/health" in main and "include_router" not in main
    assert (out / "tests" / "test_health.py").exists()
    assert (out / ".gitignore").exists()


def test_module_delivery(tmp_path):
    """[2.4.1~2.4.4] 파일 복사 + 라우터 등록 + .env 주석."""
    out = _make(tmp_path, ["jwt-auth"])
    assert (out / "src" / "routers" / "auth.py").exists()
    main = (out / "src" / "main.py").read_text(encoding="utf-8")
    assert 'prefix="/auth"' in main
    env = (out / ".env").read_text(encoding="utf-8")
    assert "# [jwt-auth]" in env and "여기에 값을 입력하세요" in env
    py = (out / "pyproject.toml").read_text(encoding="utf-8")
    assert "python-jose" in py and "fastapi" in py


def test_deterministic(tmp_path):
    """같은 입력 = 같은 결과물 (결정적 출력)."""
    a = _make(tmp_path / "run1", ["jwt-auth"], "demo")
    b = _make(tmp_path / "run2", ["jwt-auth"], "demo")
    for f in ["src/main.py", "pyproject.toml", ".env"]:
        assert (a / f).read_bytes() == (b / f).read_bytes()


def test_duplicate_dest_rejected(tmp_path):
    """[2.4.1] 같은 도착 경로면 덮어쓰지 않고 에러."""
    a = ModuleManifest(name="a", files=[FileMapping(src="f", dest="src/x.py")])
    b = ModuleManifest(name="b", files=[FileMapping(src="f", dest="src/x.py")])
    with pytest.raises(DuplicateFileError):
        copy_module_files(tmp_path, ["a", "b"], {"a": a, "b": b}, MODULES)


def test_merge_packages_dedup():
    a = ModuleManifest(name="a", pip_packages=["pydantic>=2.0"])
    b = ModuleManifest(name="b", pip_packages=["pydantic>=2.5"])
    merged = merge_packages(["a", "b"], {"a": a, "b": b})
    assert sum("pydantic" in p for p in merged) == 1


def test_merge_packages_uses_intersection_of_version_ranges():
    a = ModuleManifest(name="a", pip_packages=["pydantic>=2.0"])
    b = ModuleManifest(name="b", pip_packages=["pydantic>=2.5"])
    merged = merge_packages(["a", "b"], {"a": a, "b": b})
    assert any(pkg == "pydantic>=2.5" for pkg in merged)


def test_full_ten_module_generation(tmp_path):
    """10종 전체 선택 → 충돌 없이 생성, compose에 db·redis 서비스 포함."""
    m = load_manifests(MODULES)
    ordered = resolve(sorted(m), m)
    filtered = filter_manifests(m, {"db_type": "postgresql"})
    out = tmp_path / "full"
    generate(out, "full", ordered, filtered, MODULES, collect_env(ordered, filtered))
    compose = (out / "docker-compose.yml").read_text(encoding="utf-8")
    assert "db:" in compose and "redis:" in compose and "depends_on" in compose
    assert (out / ".github" / "workflows" / "ci.yml").exists()
    assert (out / ".dockerignore").exists()
    env = (out / ".env").read_text(encoding="utf-8")
    assert "DATABASE_URL" in env and "@db:5432" in env


def test_alembic_files_delivered(tmp_path):
    """[Alembic] database 모듈 선택 시 alembic.ini/migrations 셋업이 함께 배달된다."""
    out = _make(tmp_path, ["database"])
    assert (out / "alembic.ini").exists()
    assert (out / "migrations" / "env.py").exists()
    assert (out / "migrations" / "script.py.mako").exists()
    assert (out / "migrations" / "versions").is_dir()
    env_py = (out / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "Base.metadata" in env_py
    assert "DATABASE_URL" in env_py
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "alembic revision --autogenerate" in readme

def test_named_volumes_declared_at_top_level(tmp_path):
    """[신규] named volume(db-data 등)을 쓰는 서비스가 있으면 최상단 volumes:에도
    선언돼야 한다 — 안 그러면 docker compose가 "undefined volume"으로 거부한다."""
    out = _make(tmp_path, ["docker", "database"])
    compose = (out / "docker-compose.yml").read_text(encoding="utf-8")
    assert "\nvolumes:\n  db-data:" in compose


def test_docker_service_ports_are_env_overridable(tmp_path):
    """[신규] db/db-mysql/redis 호스트 포트는 compose 변수(${..._PORT:-기본값})로 빠져있어
    포트가 겹쳐도 .env 한 줄만 고치면 되고, .env에는 그 기본값이 채워진다.

    db_type은 실제로는 한 프로젝트에 하나만 선택되므로(postgresql/mysql이 동시에
    같이 들어가는 조합은 없음), 각각 따로 생성해서 확인한다."""
    m = load_manifests(MODULES)
    ordered = resolve(["docker", "database", "redis-cache"], m)

    pg = filter_manifests(m, {"db_type": "postgresql"})
    out_pg = tmp_path / "pg"
    generate(out_pg, "pg", ordered, pg, MODULES, collect_env(ordered, pg))
    compose_pg = (out_pg / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"${DB_PORT:-5432}:5432"' in compose_pg
    assert '"${REDIS_PORT:-6379}:6379"' in compose_pg
    env_pg = (out_pg / ".env").read_text(encoding="utf-8")
    assert "REDIS_PORT=6379" in env_pg

    mysql = filter_manifests(m, {"db_type": "mysql"})
    out_mysql = tmp_path / "mysql"
    generate(out_mysql, "mysql", ordered, mysql, MODULES, collect_env(ordered, mysql))
    compose_mysql = (out_mysql / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"${DB_PORT:-3306}:3306"' in compose_mysql



def test_compose_project_name_unique_per_generation(tmp_path):
    """[신규] docker-compose.yml에 매 생성마다 다른 프로젝트 이름이 박혀서, 폴더 이름이
    같은 두 프로젝트라도 Compose의 볼륨/네트워크 네임스페이스가 겹치지 않는다."""
    a = _make(tmp_path / "run1", ["docker"], "demo")
    b = _make(tmp_path / "run2", ["docker"], "demo")

    def _extract_name(compose_text: str) -> str:
        for line in compose_text.splitlines():
            if line.startswith("name:"):
                return line.split(":", 1)[1].strip()
        raise AssertionError("name: 줄을 못 찾음")

    name_a = _extract_name((a / "docker-compose.yml").read_text(encoding="utf-8"))
    name_b = _extract_name((b / "docker-compose.yml").read_text(encoding="utf-8"))
    assert name_a != name_b
    assert name_a.startswith("demo-") and name_b.startswith("demo-")


def test_registrations_wired(tmp_path):
    """[선택2] 등록 함수가 main.py에서 호출되는지 — 세 모듈 전부."""
    out = _make(tmp_path, ["cors", "logging", "exception-handler"])
    main = (out / "src" / "main.py").read_text(encoding="utf-8")
    assert "cors_apply(app)" in main
    assert "logging_mw_apply(app)" in main
    assert "exceptions_apply(app)" in main