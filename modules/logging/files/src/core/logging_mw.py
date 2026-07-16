"""요청 로깅 (logging 모듈).

사용법(임시): main.py 에서 `app.middleware("http")(log_requests)`
TODO(모듈 파트): registrations 필드 확정 후 자동 연결.
"""
import logging
import time

logger = logging.getLogger("app")


async def log_requests(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    logger.info("%s %s → %s (%.1fms)", request.method, request.url.path,
                response.status_code, ms)
    return response
