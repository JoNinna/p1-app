import time
import uuid
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("shopping-app")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        run_id = request.headers.get("x-run-id")
        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())

        request.state.run_id = run_id
        request.state.correlation_id = correlation_id

        status_code = 500
        error_class = None

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            error_class = exc.__class__.__name__
            raise
        finally:
            latency_ms = round((time.time() - start_time) * 1000, 2)

            logger.info(
                "request completed | run_id=%s correlation_id=%s method=%s path=%s status_code=%s latency_ms=%s error_class=%s",
                run_id,
                correlation_id,
                request.method,
                request.url.path,
                status_code,
                latency_ms,
                error_class,
            )

        response.headers["X-Correlation-Id"] = correlation_id
        return response
