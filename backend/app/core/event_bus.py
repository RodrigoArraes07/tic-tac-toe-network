import asyncio
import contextlib
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


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

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Inscreve um handler para um tipo específico de evento (ou '*' para todos)."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        """Publica um evento para todos os inscritos sem bloquear em caso de erro individual."""
        handlers = list(self._subscribers.get(event.type, [])) + list(
            self._subscribers.get("*", [])
        )

        for handler in handlers:
            with contextlib.suppress(Exception):
                asyncio.create_task(handler(event))
