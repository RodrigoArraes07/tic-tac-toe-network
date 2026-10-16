from typing import Any

from pymongo import DESCENDING
from pymongo.asynchronous.database import AsyncDatabase

EVENTS_COLLECTION = "events"


class EventRepository:
    def __init__(self, database: AsyncDatabase[dict[str, Any]]) -> None:
        self._events = database[EVENTS_COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._events.create_index([("ts", DESCENDING)])
        await self._events.create_index("type")

    async def insert(self, event: dict[str, Any]) -> None:
        await self._events.insert_one(event)
