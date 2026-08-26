"""[3.1~3.2] 충돌 검사 판정."""
from packaging.specifiers import SpecifierSet

from scaffold.engine.conflicts import check_env, check_routes, check_versions
from scaffold.engine.manifest import EnvVar, ModuleManifest, RouterSpec


def test_version_conflict():
    """버전 범위가 겹치지 않는 두 모듈은 version 충돌로 판정된다."""
    # Arrange
    a = ModuleManifest(name="a", pip_packages=["pydantic>=2.0"])
    b = ModuleManifest(name="b", pip_packages=["pydantic<2.0"])

    # Act
    found = check_versions(["a", "b"], {"a": a, "b": b})

    # Assert
    assert found and found[0].subject == "pydantic"
    assert "교집합" in found[0].detail or "겹치지" in found[0].detail


def test_version_compatible():
    """버전 범위가 겹치는 두 모듈은 충돌 없음으로 판정된다."""
    # Arrange
    a = ModuleManifest(name="a", pip_packages=["pydantic>=2.0"])
    b = ModuleManifest(name="b", pip_packages=["pydantic>=2.5"])

    # Act
    found = check_versions(["a", "b"], {"a": a, "b": b})

    # Assert
    assert found == []


def test_env_conflict():
    """같은 환경변수 이름에 기본값이 다르면 env 충돌로 판정된다."""
    # Arrange
    pairs = [("a", EnvVar(name="PORT", default="8000")),
             ("b", EnvVar(name="PORT", default="9000"))]

    # Act
    found = check_env(pairs)

    # Assert
    assert found and found[0].subject == "PORT"
    assert "기본값" in found[0].detail


def test_route_conflict():
    """같은 prefix를 쓰는 두 모듈은 라우트 충돌로 판정되고 해결 제안도 함께 온다."""
    # Arrange
    a = ModuleManifest(name="a", routers=[RouterSpec(module="x", prefix="/auth")])
    b = ModuleManifest(name="b", routers=[RouterSpec(module="y", prefix="/auth")])

    # Act
    found = check_routes(["a", "b"], {"a": a, "b": b})

    # Assert
    assert found and "중복" in found[0].detail
    assert found[0].suggestion


def test_route_conflict_detects_same_endpoint_from_different_prefixes(tmp_path):
    """manifest의 prefix가 달라도, 실제로 등록되는 최종 경로가 겹치면 충돌로 판정된다."""
    # Arrange
    modules_dir = tmp_path / "modules"
    first_dir = modules_dir / "a" / "files" / "src" / "routers"
    second_dir = modules_dir / "b" / "files" / "src" / "routers"
    first_dir.mkdir(parents=True, exist_ok=True)
    second_dir.mkdir(parents=True, exist_ok=True)

    (first_dir / "auth.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n\n"
        "@router.get(\"/users\")\ndef users():\n    return {}\n",
        encoding="utf-8",
    )
    (second_dir / "auth.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n\n"
        "@router.get(\"/api/v1/users\")\ndef users():\n    return {}\n",
        encoding="utf-8",
    )

    a = ModuleManifest(name="a", routers=[RouterSpec(module="src.routers.auth", prefix="/api/v1")])
    b = ModuleManifest(name="b", routers=[RouterSpec(module="src.routers.auth", prefix="")])

    # Act
    found = check_routes(["a", "b"], {"a": a, "b": b}, modules_dir)

    # Assert
    assert found
    assert found[0].subject == "/api/v1/users"


def test_route_conflict_detects_apirouter_prefixes(tmp_path):
    """manifest에 prefix가 없어도, 코드의 APIRouter(prefix=...)까지 반영해 충돌을 잡아낸다."""
    # Arrange
    modules_dir = tmp_path / "modules"
    first_dir = modules_dir / "a" / "files" / "src" / "routers"
    second_dir = modules_dir / "b" / "files" / "src" / "routers"
    first_dir.mkdir(parents=True, exist_ok=True)
    second_dir.mkdir(parents=True, exist_ok=True)

    (first_dir / "auth.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter(prefix=\"/api/v1\")\n\n"
        "@router.get(\"/users\")\ndef users():\n    return {}\n",
        encoding="utf-8",
    )
    (second_dir / "auth.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n\n"
        "@router.get(\"/api/v1/users\")\ndef users():\n    return {}\n",
        encoding="utf-8",
    )

    a = ModuleManifest(name="a", routers=[RouterSpec(module="src.routers.auth", prefix="")])
    b = ModuleManifest(name="b", routers=[RouterSpec(module="src.routers.auth", prefix="")])

    # Act
    found = check_routes(["a", "b"], {"a": a, "b": b}, modules_dir)

    # Assert
    assert found
    assert found[0].subject == "/api/v1/users"


def test_route_conflict_detects_include_router_paths(tmp_path):
    """include_router로 연결된 하위 라우터의 경로까지 따라가서 충돌을 잡아낸다."""
    # Arrange
    modules_dir = tmp_path / "modules"
    module_dir = modules_dir / "a" / "files" / "src" / "routers"
    module_dir.mkdir(parents=True, exist_ok=True)

    (module_dir / "inner.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n\n"
        "@router.get(\"/health\")\ndef health():\n    return {}\n",
        encoding="utf-8",
    )
    (module_dir / "main.py").write_text(
        "from fastapi import APIRouter\nfrom src.routers.inner import router as inner_router\n\n"
        "router = APIRouter()\nrouter.include_router(inner_router, prefix=\"/api/v1\")\n",
        encoding="utf-8",
    )
    (modules_dir / "b" / "files" / "src" / "routers").mkdir(parents=True, exist_ok=True)
    (modules_dir / "b" / "files" / "src" / "routers" / "other.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n\n"
        "@router.get(\"/api/v1/health\")\ndef health():\n    return {}\n",
        encoding="utf-8",
    )

    a = ModuleManifest(name="a", routers=[RouterSpec(module="src.routers.main", prefix="")])
    b = ModuleManifest(name="b", routers=[RouterSpec(module="src.routers.other", prefix="")])

    # Act
    found = check_routes(["a", "b"], {"a": a, "b": b}, modules_dir)

    # Assert
    assert found
    assert found[0].subject == "/api/v1/health"
