import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, UTC)
        event: dict[str, Any] = {
            "ts": timestamp.isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "type": record.getMessage(),
            "details": getattr(record, "details", {}),
        }
        if record.exc_info:
            event["stack"] = self.formatException(record.exc_info)
        return json.dumps(event, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


AUDIT_QUEUE_MAX_SIZE = 1000
AUDIT_LOGGER_NAME = "app.audit"
IGNORED_LOGGER_PREFIXES = ("uvicorn",)
SENSITIVE_KEYS = frozenset(
    {"password", "password_hash", "token", "access_token", "authorization", "secret", "cookie"}
)

type AuditEvent = dict[str, Any]
type AuditQueue = asyncio.Queue[AuditEvent | None]

_stack_formatter = logging.Formatter()


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize(item)
            for key, item in value.items()
            if str(key).lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, list | tuple):
        return [_sanitize(item) for item in value]
    return value


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _is_audit_record(record: logging.LogRecord) -> bool:
    if record.name == AUDIT_LOGGER_NAME or record.name.startswith(IGNORED_LOGGER_PREFIXES):
        return False
    return isinstance(getattr(record, "details", None), dict)


def _to_audit_event(record: logging.LogRecord) -> AuditEvent:
    details = _sanitize(getattr(record, "details", {}))
    if record.exc_info:
        details["stack"] = _stack_formatter.formatException(record.exc_info)
    return {
        "ts": datetime.fromtimestamp(record.created, UTC),
        "level": record.levelname,
        "type": record.getMessage(),
        "user_id": _optional_text(details.pop("user_id", None)),
        "match_id": _optional_text(details.pop("match_id", None)),
        "details": details,
    }


class AuditLogHandler(logging.Handler):
    """Copia os eventos da aplicação para a fila da auditoria sem bloquear quem loga."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.dropped = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: AuditQueue | None = None

    def bind(self, loop: asyncio.AbstractEventLoop, queue: AuditQueue) -> None:
        self._loop = loop
        self._queue = queue

    def unbind(self) -> None:
        self._loop = None
        self._queue = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if _is_audit_record(record):
                self._enqueue(_to_audit_event(record))
        except Exception:
            # Logar o próprio erro aqui voltaria para este handler.
            self.dropped += 1

    def _enqueue(self, event: AuditEvent) -> None:
        loop, queue = self._loop, self._queue
        if loop is None or queue is None or loop.is_closed():
            self.dropped += 1
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._put(queue, event)
        else:
            # asyncio.Queue não é segura entre threads: a inserção roda no loop dela.
            loop.call_soon_threadsafe(self._put, queue, event)

    def _put(self, queue: AuditQueue, event: AuditEvent) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1
