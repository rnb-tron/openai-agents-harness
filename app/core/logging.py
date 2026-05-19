import json
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from app.settings import current_settings

_log_dir = os.getenv("MATRIX_APPLOGS_DIR", "app/logs")
os.makedirs(_log_dir, exist_ok=True)

_rid_var: ContextVar[str | None] = ContextVar("rid", default=None)
_log_context_var: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})


def new_rid() -> str:
    return uuid.uuid4().hex


def get_rid() -> str | None:
    return _rid_var.get()


def set_rid(rid: str | None = None):
    return _rid_var.set(rid or new_rid())


def reset_rid(token) -> None:
    _rid_var.reset(token)


def bind_log_context(**fields: Any):
    context = dict(_log_context_var.get())
    context.update({key: value for key, value in fields.items() if value is not None})
    return _log_context_var.set(context)


def reset_log_context(token) -> None:
    _log_context_var.reset(token)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.rid = get_rid() or "-"
        record.context = dict(_log_context_var.get())
        return True


def _single_line_text(value: str) -> str:
    return value.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\r")


def _log_safe(value: Any) -> Any:
    if isinstance(value, str):
        return _single_line_text(value)
    if isinstance(value, dict):
        return {str(key): _log_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_log_safe(item) for item in value]
    return value


def _compact_json(data: Any) -> str:
    return json.dumps(_log_safe(data), ensure_ascii=False, default=str, separators=(",", ":"))


class SingleLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base_msg = super().format(record)
        event = getattr(record, "event", None)
        fields = getattr(record, "structured_fields", None)
        if event or fields:
            extras = []
            if event:
                extras.append(f"event={event}")
            if fields:
                extras.append(f"fields={_compact_json(fields)}")
            base_msg = f"{base_msg} | {' '.join(extras)}"
        return _single_line_text(base_msg)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": _single_line_text(record.getMessage()),
            "rid": getattr(record, "rid", "-"),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        context = getattr(record, "context", None)
        if context:
            payload["context"] = _log_safe(context)
        event = getattr(record, "event", None)
        if event:
            payload["event"] = event
        fields = getattr(record, "structured_fields", None)
        if fields:
            payload["fields"] = _log_safe(fields)
        if record.exc_info:
            payload["exc_info"] = _single_line_text(self.formatException(record.exc_info))
        return _compact_json(payload)


def _resolve_log_file(log_file: str | None, default_name: str) -> str:
    if not log_file:
        return os.path.join(_log_dir, default_name)
    path = Path(log_file)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
    except OSError:
        return os.path.join(_log_dir, path.name)


def setup_logger(name: str, log_file: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, current_settings.log_level.upper()))
    formatter = SingleLineFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - [rid=%(rid)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    context_filter = RequestContextFilter()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)
    logger.addHandler(console_handler)

    file_handler = TimedRotatingFileHandler(
        _resolve_log_file(log_file, "default.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=False,
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonLogFormatter())
    file_handler.addFilter(context_filter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, event, extra={"event": event, "structured_fields": _log_safe(fields)})


api_logger = setup_logger("api")
service_logger = setup_logger("service")
proxy_logger = setup_logger("proxy")
error_logger = setup_logger("error")
