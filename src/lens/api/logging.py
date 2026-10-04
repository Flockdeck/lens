"""JSON logging. Records carry ids, counts and timings only; never recording content."""

import json
import logging
import os
import sys
import traceback
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
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


LOG_FILE_BYTES = 5 * 1024 * 1024
LOG_FILE_COUNT = 3


def log_destination(log_file: str, data_dir: str) -> Path | None:
    """Where logs go: None for standard output, else a file.

    * LOG_FILE=-            standard output.
    * LOG_FILE=<path>       that file.
    * unset, in a terminal  standard output, so a person running it sees what happens.
    * unset, not a terminal a file in the data directory. A program that starts lens and
      reads its output through a pipe it never empties would otherwise freeze it the moment the
      pipe fills, since every request is logged.
    """
    if log_file == "-":
        return None
    if log_file:
        return Path(log_file).expanduser()
    if sys.stdout is not None and sys.stdout.isatty():
        return None
    return Path(data_dir).expanduser() / "lens.log"


def setup_logging(level: str = "INFO", log_file: str = "-", data_dir: str = ".") -> None:
    destination = log_destination(log_file, data_dir)
    handler: logging.Handler
    if destination is None:
        handler = logging.StreamHandler(sys.stdout)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            destination, maxBytes=LOG_FILE_BYTES, backupCount=LOG_FILE_COUNT, encoding="utf-8"
        )
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
