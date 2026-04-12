import logging
import time
import uuid

from fastapi import Request
from opentelemetry import trace
from opentelemetry.trace import format_trace_id
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("shopping-app")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()

        run_id = request.headers.get("x-run-id")
        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())

        request.state.run_id = run_id
        request.state.correlation_id = correlation_id

        logger.info(
            "incoming request | run_id=%s correlation_id=%s method=%s path=%s",
            run_id,
            correlation_id,
            request.method,
            request.url.path,
        )

        status_code = 500
        error_class = None

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            error_class = exc.__class__.__name__
            raise
        finally:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

            span = trace.get_current_span()
            span_ctx = span.get_span_context()

            trace_id = None
            if span_ctx and span_ctx.trace_id:
                trace_id = format_trace_id(span_ctx.trace_id)

            if span is not None:
                span.set_attribute("app.correlation_id", correlation_id)
                if run_id:
                    span.set_attribute("app.run_id", run_id)
                span.set_attribute("http.request.method", request.method)
                span.set_attribute("url.path", request.url.path)

            logger.info(
                "request completed | run_id=%s correlation_id=%s trace_id=%s method=%s path=%s status_code=%s latency_ms=%s error_class=%s",
                run_id,
                correlation_id,
                trace_id,
                request.method,
                request.url.path,
                status_code,
                latency_ms,
                error_class,
            )

        response.headers["X-Correlation-Id"] = correlation_id
        if run_id:
            response.headers["X-Run-Id"] = run_id

        return response
