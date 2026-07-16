"""[2.3~2.5] 생성 검증: 최소 뼈대 · 배달 · 결정적 출력."""
from pathlib import Path

import pytest

from scaffold.engine.errors import DuplicateFileError
from scaffold.engine.generator import copy_module_files, generate, merge_packages
from scaffold.engine.loader import load_manifests
from scaffold.engine.manifest import FileMapping, ModuleManifest
from scaffold.engine.resolver import collect_env, resolve

MODULES = Path(__file__).parents[1] / "modules"


def _make(tmp_path: Path, selected: list[str], name="demo") -> Path:
    m = load_manifests(MODULES)
    ordered = resolve(selected, m) if selected else []
    out = tmp_path / name
    generate(out, name, ordered, m, MODULES, collect_env(ordered, m))
    return out


def test_bare_skeleton(tmp_path):
    """[2.3.1] 완료 기준: 모듈 0개여도 /health 앱과 기본 테스트가 존재."""
    out = _make(tmp_path, [])
    main = (out / "src" / "main.py").read_text()
    assert "/health" in main and "include_router" not in main
    assert (out / "tests" / "test_health.py").exists()
    assert (out / ".gitignore").exists()


def test_module_delivery(tmp_path):
    """[2.4.1~2.4.4] 파일 복사 + 라우터 등록 + .env 주석."""
    out = _make(tmp_path, ["jwt-auth"])
    assert (out / "src" / "routers" / "auth.py").exists()
    main = (out / "src" / "main.py").read_text()
    assert 'prefix="/auth"' in main
    env = (out / ".env").read_text()
    assert "# [jwt-auth]" in env and "여기에 값을 입력하세요" in env
    py = (out / "pyproject.toml").read_text()
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


def test_full_ten_module_generation(tmp_path):
    """10종 전체 선택 → 충돌 없이 생성, compose에 db·redis 서비스 포함."""
    m = load_manifests(MODULES)
    ordered = resolve(sorted(m), m)
    out = tmp_path / "full"
    generate(out, "full", ordered, m, MODULES, collect_env(ordered, m))
    compose = (out / "docker-compose.yml").read_text()
    assert "db:" in compose and "redis:" in compose and "depends_on" in compose
    assert (out / ".github" / "workflows" / "ci.yml").exists()
    assert (out / ".dockerignore").exists()
    env = (out / ".env").read_text()
    assert "DATABASE_URL" in env and "@db:5432" in env
