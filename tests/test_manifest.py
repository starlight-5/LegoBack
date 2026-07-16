"""[2.2.1] manifest 파싱 검증."""
from pathlib import Path

from scaffold.engine.loader import load_manifests

MODULES = Path(__file__).parents[1] / "modules"


def test_load_all_manifests():
    m = load_manifests(MODULES)
    assert "settings" in m and "jwt-auth" in m
    assert m["jwt-auth"].depends_on == ["settings"]
    assert m["jwt-auth"].routers[0].prefix == "/auth"


def test_all_ten_modules_present():
    """RFP 확정 10종이 모두 로드되는지 검증."""
    m = load_manifests(MODULES)
    expected = {"jwt-auth", "rbac", "database", "exception-handler", "logging",
                "cors", "settings", "docker", "ci", "redis-cache"}
    assert expected <= set(m)
