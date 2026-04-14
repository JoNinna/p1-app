import json
import logging
import os
from datetime import datetime, timezone


SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "shopping-app")
APP_ENV = os.getenv("APP_ENV", "dev")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", SERVICE_NAME),
            "env": getattr(record, "env", APP_ENV),
            "run_id": getattr(record, "run_id", None),
            "correlation_id": getattr(record, "correlation_id", None),
            "trace_id": getattr(record, "trace_id", None),
            "status_code": getattr(record, "status_code", None),
            "error_class": getattr(record, "error_class", None),
            "latency_ms": getattr(record, "latency_ms", None),
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "user": getattr(record, "user", None),
            "roles": getattr(record, "roles", None),
        }
        return json.dumps(log_record, default=str)


def setup_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
