"""[2.2.2] 의존성 그래프: 자동 포함 · 순환 감지 · 순서."""
from pathlib import Path

import pytest

from scaffold.engine.errors import CircularDependencyError, ScaffoldError
from scaffold.engine.loader import load_manifests
from scaffold.engine.manifest import EnvVar, ModuleManifest
from scaffold.engine.resolver import collect_env, filter_manifests, resolve

MODULES = Path(__file__).parents[1] / "modules"


def test_cycle_detected():
    """서로를 의존하는 순환 구조는 CircularDependencyError를 던진다."""
    # Arrange
    a = ModuleManifest(name="a", depends_on=["b"])
    b = ModuleManifest(name="b", depends_on=["a"])

    # Act & Assert
    with pytest.raises(CircularDependencyError):
        resolve(["a"], {"a": a, "b": b})


def test_resolve_auto_includes_dependency():
    """선택한 모듈이 의존하는 모듈을 자동으로 포함하고, 의존받는 쪽을 먼저 배치한다."""
    # Arrange
    a = ModuleManifest(name="a", depends_on=["b"])
    b = ModuleManifest(name="b")

    # Act
    ordered = resolve(["a"], {"a": a, "b": b})

    # Assert
    assert ordered == ["b", "a"]


def test_resolve_diamond_dependency_included_once():
    """a,b가 둘 다 d에 의존하면, d는 결과에 한 번만 나오고 a·b보다 앞에 온다."""
    # Arrange
    a = ModuleManifest(name="a", depends_on=["b", "c"])
    b = ModuleManifest(name="b", depends_on=["d"])
    c = ModuleManifest(name="c", depends_on=["d"])
    d = ModuleManifest(name="d")

    # Act
    ordered = resolve(["a"], {"a": a, "b": b, "c": c, "d": d})

    # Assert
    assert ordered.count("d") == 1
    assert ordered.index("d") < ordered.index("b") < ordered.index("a")
    assert ordered.index("d") < ordered.index("c") < ordered.index("a")


def test_resolve_unknown_module_raises():
    """manifests에 없는 모듈명을 선택하면 ScaffoldError를 던진다."""
    # Arrange
    a = ModuleManifest(name="a")

    # Act & Assert
    with pytest.raises(ScaffoldError):
        resolve(["no-such-module"], {"a": a})


def test_collect_env_preserves_module_order_and_all_vars():
    """env_vars를 모듈 순서·선언 순서 그대로 수집한다."""
    # Arrange
    a = ModuleManifest(name="a", env_vars=[EnvVar(name="A1"), EnvVar(name="A2")])
    b = ModuleManifest(name="b", env_vars=[EnvVar(name="B1")])

    # Act
    pairs = collect_env(["a", "b"], {"a": a, "b": b})

    # Assert
    assert [(mod, var.name) for mod, var in pairs] == [("a", "A1"), ("a", "A2"), ("b", "B1")]


@pytest.mark.integration
def test_auto_include_dependency():
    """실제 jwt-auth manifest의 depends_on(settings, database)이 그대로 해석되는지 확인."""
    m = load_manifests(MODULES)
    ordered = resolve(["jwt-auth"], m)                       # settings, database 자동 포함
    assert ordered == ["settings", "database", "jwt-auth"]   # 의존받는 쪽 먼저


@pytest.mark.integration
def test_collect_env_order():
    """실제 jwt-auth/database manifest의 env_vars 선언 순서가 그대로 수집되는지 확인."""
    m = load_manifests(MODULES)
    ordered = resolve(["jwt-auth"], m)
    filtered = filter_manifests(m, {"db_type": "postgresql"})
    pairs = collect_env(ordered, filtered)
    names = [v.name for _, v in pairs]
    assert names == [
        "APP_ENV", "DATABASE_URL", "DB_PORT",
        "JWT_SECRET_KEY", "JWT_ACCESS_MINUTES", "JWT_REFRESH_MINUTES",
    ]
