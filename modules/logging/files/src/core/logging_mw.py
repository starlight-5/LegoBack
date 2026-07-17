"""요청 로깅 (logging 모듈).

모든 요청의 메서드·경로·상태·소요 시간을 기록한다.
등록: manifest의 registrations에 선언된 apply(app)를 엔진이 main.py에서 호출한다.
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


def apply(app):
    """logging 모듈 등록 함수: 요청 로깅 미들웨어를 통로에 끼운다."""
    app.middleware("http")(log_requests)