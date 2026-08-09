"""Structured JSON logging for production.

A small stdlib-only ``JSONFormatter`` that serialises each log record as one
JSON object per line — machine-parseable by any log shipper (CloudWatch,
Datadog, loki, etc.). ``asctime``/``name``/``levelname``/``message`` are the
stable keys; ``extra`` fields passed to the logger are merged in so callers
can attach request ids, user ids, task names, etc. without extra machinery.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

RESERVED = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JSONFormatter(logging.Formatter):
    """Serialize log records as newline-delimited JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": dt.datetime.fromtimestamp(record.created, tz=dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # Merge caller-supplied extras (e.g. {"request_id": ..., "user_id": ...})
        # so structured fields survive into the log line.
        for key, value in record.__dict__.items():
            if key not in RESERVED and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)

        return json.dumps(payload, default=str)
