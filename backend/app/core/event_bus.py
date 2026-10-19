import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Event:
    type: str
    data: dict[str, Any]
    user_id: str | None = None
    match_id: str | None = None
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        # Referência forte: sem ela o asyncio pode descartar a task antes de terminar.
        self._tasks: set[asyncio.Task[None]] = set()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Inscreve um handler para um tipo específico de evento (ou '*' para todos)."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def has_subscribers(self, event_type: str) -> bool:
        """Só conta handlers do tipo exato; os curinga '*' não tratam um comando."""
        return bool(self._subscribers.get(event_type))

    async def publish(self, event: Event) -> None:
        """Publica um evento para todos os inscritos sem bloquear em caso de erro individual."""
        handlers = list(self._subscribers.get(event.type, [])) + list(
            self._subscribers.get("*", [])
        )

        for handler in handlers:
            task = asyncio.create_task(self._run(handler, event))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _run(self, handler: EventHandler, event: Event) -> None:
        try:
            await handler(event)
        except Exception:
            details = {
                "component": "event_bus",
                "event": event.type,
                "handler": _handler_name(handler),
            }
            logger.error("error.internal", extra={"details": details}, exc_info=True)


def _handler_name(handler: EventHandler) -> str:
    target = getattr(handler, "func", handler)
    return getattr(target, "__qualname__", repr(target))
