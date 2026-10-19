import asyncio
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from app.core.logging import AuditLogHandler, AuditQueue
from app.services.audit import AuditService


class FailingRepository:
    async def insert(self, event: dict[str, Any]) -> None:
        raise RuntimeError("banco fora do ar")


@pytest.fixture
def isolated_logger() -> Iterator[logging.Logger]:
    logger = logging.getLogger("tests.audit.unit")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    yield logger
    logger.handlers.clear()
    logger.propagate = True


async def test_full_queue_drops_the_event_without_raising(
    isolated_logger: logging.Logger,
) -> None:
    queue: AuditQueue = asyncio.Queue(maxsize=1)
    handler = AuditLogHandler()
    handler.bind(asyncio.get_running_loop(), queue)
    isolated_logger.addHandler(handler)

    isolated_logger.info("teste.primeiro", extra={"details": {}})
    isolated_logger.info("teste.segundo", extra={"details": {}})

    assert queue.qsize() == 1
    assert handler.dropped == 1


async def test_write_failure_is_logged_without_feeding_the_queue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue: AuditQueue = asyncio.Queue()
    handler = AuditLogHandler()
    handler.bind(asyncio.get_running_loop(), queue)
    root = logging.getLogger()
    root.addHandler(handler)
    service = AuditService(FailingRepository(), queue)
    try:
        await queue.put({"type": "teste.falha", "details": {}})
        service.start()
        with caplog.at_level(logging.ERROR):
            await service.stop()
    finally:
        root.removeHandler(handler)

    failures = [r for r in caplog.records if r.getMessage() == "error.internal"]
    assert queue.qsize() == 0
    assert handler.dropped == 0
    assert [getattr(r, "details", {}).get("component") for r in failures] == ["audit"]
