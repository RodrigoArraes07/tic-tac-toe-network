import asyncio
import logging

import pytest

from app.core.event_bus import Event, EventBus

EVENT_TYPE = "cmd.teste"


async def failing_handler(event: Event) -> None:
    raise RuntimeError("falha simulada")


async def test_failing_handler_is_logged_and_does_not_stop_the_others(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    received: list[Event] = []

    async def recording_handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EVENT_TYPE, failing_handler)
    bus.subscribe(EVENT_TYPE, recording_handler)
    event = Event(type=EVENT_TYPE, data={})

    with caplog.at_level(logging.ERROR):
        await bus.publish(event)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    errors = [record for record in caplog.records if record.getMessage() == "error.internal"]
    assert received == [event]
    assert len(errors) == 1
    assert getattr(errors[0], "details", None) == {
        "component": "event_bus",
        "event": EVENT_TYPE,
        "handler": "failing_handler",
    }
    assert errors[0].exc_info is not None
