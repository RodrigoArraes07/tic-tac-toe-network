import asyncio
import contextlib
import logging

from app.core.logging import AUDIT_LOGGER_NAME, AuditEvent, AuditQueue
from app.repositories.events import EventRepository

AUDIT_DRAIN_TIMEOUT_SECONDS = 5.0

# Logger ignorado pelo AuditLogHandler: uma falha ao gravar não volta para a fila.
logger = logging.getLogger(AUDIT_LOGGER_NAME)


class AuditService:
    """Grava na coleção events, em segundo plano, os eventos que chegam pela fila."""

    def __init__(self, repository: EventRepository, queue: AuditQueue) -> None:
        self._repository = repository
        self._queue = queue
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Esvazia a fila antes de encerrar; um banco fora do ar não trava o desligamento."""
        task = self._task
        if task is None:
            return
        try:
            await asyncio.wait_for(self._drain(task), AUDIT_DRAIN_TIMEOUT_SECONDS)
        except TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            details = {"component": "audit", "pending": self._queue.qsize()}
            logger.warning("audit.drain_timeout", extra={"details": details})
        self._task = None

    async def _drain(self, task: asyncio.Task[None]) -> None:
        await self._queue.put(None)
        await task

    async def _run(self) -> None:
        while (event := await self._queue.get()) is not None:
            await self._save(event)

    async def _save(self, event: AuditEvent) -> None:
        try:
            await self._repository.insert(event)
        except Exception:
            details = {"component": "audit", "type": event.get("type")}
            logger.error("error.internal", extra={"details": details}, exc_info=True)
