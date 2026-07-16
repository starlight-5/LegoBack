from src.core.config import get_settings


def test_settings_loads():
    assert get_settings().APP_ENV in {"development", "production"}
