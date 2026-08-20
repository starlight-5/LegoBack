"""캐시 CRUD·@cached·invalidate 동작 테스트 (redis-cache 모듈)."""
import fnmatch

import pytest

from src.core import cache as cache_module


class _FakeRedis:
    """실제 redis 서버 없이 테스트하기 위한 최소 in-memory 대역. TTL은 값 대신 기록만 한다."""

    def __init__(self):
        self._store: dict[str, bytes] = {}
        self.last_ex: int | None = None

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value, ex: int | None = None):
        self._store[key] = value.encode() if isinstance(value, str) else value
        self.last_ex = ex

    def delete(self, *keys: str):
        for k in keys:
            self._store.pop(k, None)

    def scan_iter(self, match: str):
        return [k for k in list(self._store) if fnmatch.fnmatch(k, match)]


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(cache_module, "get_redis", lambda: fake)
    return fake


def test_set_then_get_roundtrip():
    cache_module.cache_set("k1", {"a": 1})
    assert cache_module.cache_get("k1") == {"a": 1}


def test_get_missing_key_returns_none():
    assert cache_module.cache_get("missing") is None


def test_set_passes_ttl_to_redis(fake_redis):
    cache_module.cache_set("k2", "v", ttl=30)
    assert fake_redis.last_ex == 30


def test_delete_removes_key():
    cache_module.cache_set("k3", "v")
    cache_module.cache_delete("k3")
    assert cache_module.cache_get("k3") is None


def test_invalidate_removes_matching_keys_only():
    cache_module.cache_set("user:1:profile", "a")
    cache_module.cache_set("user:1:orders", "b")
    cache_module.cache_set("user:2:profile", "c")

    cache_module.cache_invalidate("user:1:*")

    assert cache_module.cache_get("user:1:profile") is None
    assert cache_module.cache_get("user:1:orders") is None
    assert cache_module.cache_get("user:2:profile") == "c"


def test_cached_decorator_reuses_result_for_same_args():
    calls = []

    @cache_module.cached(ttl=60)
    def compute(x):
        calls.append(x)
        return x * 2

    assert compute(3) == 6
    assert compute(3) == 6
    assert calls == [3]


def test_cached_decorator_distinguishes_different_args():
    @cache_module.cached(ttl=60)
    def compute(x):
        return x * 2

    assert compute(3) == 6
    assert compute(4) == 8


