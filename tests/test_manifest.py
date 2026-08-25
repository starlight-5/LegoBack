"""[2.2.1] manifest 파싱 검증."""
from pathlib import Path

import pytest

from scaffold.engine.loader import load_manifests

MODULES = Path(__file__).parents[1] / "modules"


@pytest.mark.integration
def test_load_all_manifests():
    """실제 modules/ 전체를 로드해 depends_on·routers·registrations 필드가 올바르게 파싱되는지 확인."""
    m = load_manifests(MODULES)
    assert "settings" in m and "jwt-auth" in m
    assert m["jwt-auth"].depends_on == ["settings", "database"]
    assert m["jwt-auth"].routers[0].prefix == "/auth"
    assert m["cors"].registrations == ["src.core.cors.apply"]


@pytest.mark.integration
def test_all_ten_modules_present():
    """RFP 확정 10종이 모두 로드되는지 검증."""
    m = load_manifests(MODULES)
    expected = {"jwt-auth", "rbac", "database", "exception-handler", "logging",
                "cors", "settings", "docker", "ci", "redis-cache"}
    assert expected <= set(m)
