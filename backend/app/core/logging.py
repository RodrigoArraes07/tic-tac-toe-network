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
