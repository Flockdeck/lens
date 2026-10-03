"""JSON logging. Records carry ids, counts and timings only; never recording content."""

import json
import logging
import os
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

# LogRecord attributes that are not caller-supplied context.
_STANDARD = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD:
                payload[key] = value
        if record.exc_info and record.exc_info[0]:
            # Exception type and file:line frames only. Messages can echo user-supplied
            # (recording) content, and source lines are not needed to locate the error.
            payload["exc_type"] = record.exc_info[0].__name__
            payload["frames"] = [
                f"{os.path.basename(f.filename)}:{f.lineno} {f.name}"
                for f in traceback.extract_tb(record.exc_info[2])
            ]
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # uvicorn's access log includes query strings; the app logs its own request line instead.
    logging.getLogger("uvicorn.access").disabled = True
    quiet_database_loggers()


def quiet_database_loggers() -> None:
    """aiosqlite logs every statement WITH its parameters at DEBUG, which would put an API key
    (a row in app_settings) and recording content in the log whatever LOG_LEVEL says."""
    for name in ("aiosqlite", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
