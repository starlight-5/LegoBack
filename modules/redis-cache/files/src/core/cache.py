"""Redis 캐시 (redis-cache 모듈)."""
import json
import os
from functools import lru_cache, wraps
from typing import Any, Callable

import redis


@lru_cache
def get_redis() -> redis.Redis:
    return redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))


def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    """값을 JSON으로 직렬화해 저장. ttl(초) 지정 시 그 시간 뒤 자동 만료."""
    get_redis().set(key, json.dumps(value), ex=ttl)


def cache_get(key: str) -> Any | None:
    """저장된 값을 역직렬화해 반환. 키가 없으면 None."""
    raw = get_redis().get(key)
    return json.loads(raw) if raw is not None else None


def cache_delete(*keys: str) -> None:
    """키를 하나 이상 삭제."""
    if keys:
        get_redis().delete(*keys)


def cache_invalidate(pattern: str) -> None:
    """패턴에 매칭되는 키를 전부 삭제 (예: "user:123:*")."""
    keys = list(get_redis().scan_iter(match=pattern))
    if keys:
        get_redis().delete(*keys)


def _build_key(prefix: str, args: tuple, kwargs: dict) -> str:
    parts = [prefix, *map(str, args), *(f"{k}={v}" for k, v in sorted(kwargs.items()))]
    return ":".join(parts)


def cached(ttl: int = 60, key_prefix: str = "") -> Callable:
    """함수 결과를 캐싱하는 데코레이터. 인자로 캐시 키를 자동 생성한다."""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            #1. 키 생성 
            key = _build_key(key_prefix or func.__name__, args, kwargs)
            #2. 캐시 조회
            hit = cache_get(key)
            #3. 캐시가 있으면 저장된 캐시값 반환
            if hit is not None:
                return hit
            #4. 캐시가 없으면 함수 실행
            result = func(*args, **kwargs)
            #5. 캐시에 키와 함수 결과 저장
            cache_set(key, result, ttl=ttl)
            #6. 저장한 캐시 값 반환
            return result
        return wrapper
    return decorator


