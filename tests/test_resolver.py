"""[2.2.2] 의존성 그래프: 자동 포함 · 순환 감지 · 순서."""
from pathlib import Path

import pytest

from scaffold.engine.errors import CircularDependencyError, ScaffoldError
from scaffold.engine.loader import load_manifests
from scaffold.engine.manifest import ModuleManifest
from scaffold.engine.resolver import collect_env, resolve

MODULES = Path(__file__).parents[1] / "modules"


def test_auto_include_dependency():
    m = load_manifests(MODULES)
    ordered = resolve(["jwt-auth"], m)          # settings 자동 포함
    assert ordered == ["settings", "jwt-auth"]  # 의존받는 쪽 먼저


def test_unknown_module():
    m = load_manifests(MODULES)
    with pytest.raises(ScaffoldError):
        resolve(["no-such-module"], m)


def test_cycle_detected():
    a = ModuleManifest(name="a", depends_on=["b"])
    b = ModuleManifest(name="b", depends_on=["a"])
    with pytest.raises(CircularDependencyError):
        resolve(["a"], {"a": a, "b": b})


def test_collect_env_order():
    m = load_manifests(MODULES)
    pairs = collect_env(resolve(["jwt-auth"], m), m)
    names = [v.name for _, v in pairs]
    assert names == ["APP_ENV", "JWT_SECRET_KEY", "JWT_ACCESS_MINUTES"]
