"""[3.1~3.2] 충돌 검사 판정."""
from scaffold.engine.conflicts import check_env, check_routes, check_versions
from scaffold.engine.manifest import EnvVar, ModuleManifest, RouterSpec


def test_version_conflict():
    a = ModuleManifest(name="a", pip_packages=["pydantic>=2.0"])
    b = ModuleManifest(name="b", pip_packages=["pydantic<2.0"])
    found = check_versions(["a", "b"], {"a": a, "b": b})
    assert found and found[0].subject == "pydantic"


def test_version_compatible():
    a = ModuleManifest(name="a", pip_packages=["pydantic>=2.0"])
    b = ModuleManifest(name="b", pip_packages=["pydantic>=2.5"])
    assert check_versions(["a", "b"], {"a": a, "b": b}) == []


def test_env_conflict():
    pairs = [("a", EnvVar(name="PORT", default="8000")),
             ("b", EnvVar(name="PORT", default="9000"))]
    found = check_env(pairs)
    assert found and found[0].subject == "PORT"


def test_route_conflict():
    a = ModuleManifest(name="a", routers=[RouterSpec(module="x", prefix="/auth")])
    b = ModuleManifest(name="b", routers=[RouterSpec(module="y", prefix="/auth")])
    assert check_routes(["a", "b"], {"a": a, "b": b})
