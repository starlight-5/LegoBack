"""Redis 캐시 (redis-cache 모듈).

TODO(모듈 파트): TTL 옵션, 캐시 데코레이터(@cached) 제공.
"""
import os
from functools import lru_cache

import redis


@lru_cache
def get_redis() -> redis.Redis:
    return redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
