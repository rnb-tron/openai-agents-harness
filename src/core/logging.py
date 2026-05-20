import json
import logging
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from src.core.config import current_settings

_log_dir = os.getenv("MATRIX_APPLOGS_DIR", "data/logs")
os.makedirs(_log_dir, exist_ok=True)

_rid_var: ContextVar[str | None] = ContextVar("rid", default=None)
_log_context_var: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})

# 敏感字段列表 (自动脱敏)
SENSITIVE_FIELDS = {
    "api_key", "secret", "password", "token", "authorization",
    "access_token", "refresh_token", "secret_key", "private_key",
    "credit_card", "card_number", "cvv",
    "phone", "mobile", "email", "id_card", "id_number",
    "bank_account", "account_number"
}


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


def _sanitize_value(field: str, value: Any) -> Any:
    """脱敏敏感字段值"""
    if field.lower() in SENSITIVE_FIELDS:
        if isinstance(value, str):
            if len(value) <= 8:
                return "***"
            return value[:4] + "***" + value[-4:]
        return "***"
    return value


def _sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """递归脱敏字典中的所有敏感字段"""
    if not isinstance(data, dict):
        return data
    
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, dict):
            sanitized[key] = _sanitize_dict(value)
        elif isinstance(value, (list, tuple)):
            sanitized[key] = [
                _sanitize_dict(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = _sanitize_value(key, value)
    return sanitized


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
        
        # 添加事件信息
        event = getattr(record, "event", None)
        if event:
            payload["event"] = event
        
        # 添加结构化字段 (自动脱敏)
        fields = getattr(record, "structured_fields", None)
        if fields:
            payload["fields"] = _sanitize_dict(_log_safe(fields))
        
        # 添加异常信息 (结构化)
        if record.exc_info:
            payload["exc_info"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]) if record.exc_info[1] else "",
            }
        
        # 添加元数据
        payload["metadata"] = {
            "app_version": os.getenv("APP_VERSION", "unknown"),
            "env": current_settings.env_type,
        }
        
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
    """记录结构化事件日志 (便捷函数)"""
    logger.log(level, event, extra={"event": event, "structured_fields": _log_safe(fields)})


@contextmanager
def log_context(session_id: str | None = None, user_id: str | None = None, **fields):
    """日志上下文管理器
    
    Example:
        with log_context(session_id="session-001", user_id="user-123"):
            service_logger.info("处理请求")  # 自动包含 session_id 和 user_id
    """
    token = bind_log_context(session_id=session_id, user_id=user_id, **fields)
    try:
        yield
    finally:
        reset_log_context(token)


api_logger = setup_logger("api")
service_logger = setup_logger("service")
proxy_logger = setup_logger("proxy")
error_logger = setup_logger("error")
