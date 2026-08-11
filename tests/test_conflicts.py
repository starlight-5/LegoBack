"""[3.1~3.2] 충돌 검사 판정."""
from packaging.specifiers import SpecifierSet

from scaffold.engine.conflicts import check_env, check_routes, check_versions
from scaffold.engine.manifest import EnvVar, ModuleManifest, RouterSpec


def test_version_conflict():
    a = ModuleManifest(name="a", pip_packages=["pydantic>=2.0"])
    b = ModuleManifest(name="b", pip_packages=["pydantic<2.0"])
    found = check_versions(["a", "b"], {"a": a, "b": b})
    assert found and found[0].subject == "pydantic"
    assert "교집합" in found[0].detail or "겹치지" in found[0].detail


def test_version_compatible():
    a = ModuleManifest(name="a", pip_packages=["pydantic>=2.0"])
    b = ModuleManifest(name="b", pip_packages=["pydantic>=2.5"])
    assert check_versions(["a", "b"], {"a": a, "b": b}) == []


def test_env_conflict():
    pairs = [("a", EnvVar(name="PORT", default="8000")),
             ("b", EnvVar(name="PORT", default="9000"))]
    found = check_env(pairs)
    assert found and found[0].subject == "PORT"
    assert "기본값" in found[0].detail


def test_route_conflict():
    a = ModuleManifest(name="a", routers=[RouterSpec(module="x", prefix="/auth")])
    b = ModuleManifest(name="b", routers=[RouterSpec(module="y", prefix="/auth")])
    found = check_routes(["a", "b"], {"a": a, "b": b})
    assert found and "중복" in found[0].detail


def test_route_conflict_detects_same_endpoint_from_different_prefixes(tmp_path):
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

    found = check_routes(["a", "b"], {"a": a, "b": b}, modules_dir)
    assert found
    assert found[0].subject == "/api/v1/users"


def test_route_conflict_provides_suggestion():
    a = ModuleManifest(name="a", routers=[RouterSpec(module="x", prefix="/auth")])
    b = ModuleManifest(name="b", routers=[RouterSpec(module="y", prefix="/auth")])
    found = check_routes(["a", "b"], {"a": a, "b": b})
    assert found and found[0].suggestion


def test_route_conflict_detects_apirouter_prefixes(tmp_path):
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

    found = check_routes(["a", "b"], {"a": a, "b": b}, modules_dir)
    assert found
    assert found[0].subject == "/api/v1/users"


def test_route_conflict_detects_include_router_paths(tmp_path):
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

    found = check_routes(["a", "b"], {"a": a, "b": b}, modules_dir)
    assert found
    assert found[0].subject == "/api/v1/health"
