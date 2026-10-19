import logging
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

type MongoClient = AsyncMongoClient[dict[str, Any]]


def create_client(uri: str) -> MongoClient:
    return AsyncMongoClient(uri)


async def ping(client: MongoClient) -> bool:
    try:
        await client.admin.command("ping")
    except PyMongoError as exc:
        details = {"component": "database", "message": type(exc).__name__}
        logger.error("error.internal", extra={"details": details}, exc_info=True)
        return False
    return True
