from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

USERS_COLLECTION = "users"


class DuplicateUsernameError(Exception):
    pass


@dataclass(frozen=True)
class UserStats:
    wins: int = 0
    losses: int = 0
    draws: int = 0
    points: int = 0


@dataclass(frozen=True)
class User:
    id: str
    username: str
    password_hash: str
    created_at: datetime
    last_login_at: datetime | None
    stats: UserStats


def _to_user(document: dict[str, Any]) -> User:
    return User(
        id=str(document["_id"]),
        username=document["username"],
        password_hash=document["password_hash"],
        created_at=document["created_at"],
        last_login_at=document["last_login_at"],
        stats=UserStats(**document["stats"]),
    )


def _to_object_id(user_id: str) -> ObjectId | None:
    try:
        return ObjectId(user_id)
    except InvalidId, TypeError:
        return None


class UserRepository:
    def __init__(self, database: AsyncDatabase[dict[str, Any]]) -> None:
        self._users = database[USERS_COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._users.create_index("username", unique=True)

    async def find_by_username(self, username: str) -> User | None:
        document = await self._users.find_one({"username": username.lower()})
        return _to_user(document) if document else None

    async def find_by_id(self, user_id: str) -> User | None:
        object_id = _to_object_id(user_id)
        if object_id is None:
            return None
        document = await self._users.find_one({"_id": object_id})
        return _to_user(document) if document else None

    async def insert(self, username: str, password_hash: str, created_at: datetime) -> User:
        document: dict[str, Any] = {
            "username": username.lower(),
            "password_hash": password_hash,
            "created_at": created_at,
            "last_login_at": None,
            "stats": {"wins": 0, "losses": 0, "draws": 0, "points": 0},
        }
        try:
            await self._users.insert_one(document)
        except DuplicateKeyError as exc:
            raise DuplicateUsernameError from exc
        return _to_user(document)

    async def update_last_login(self, user_id: str, logged_in_at: datetime) -> None:
        await self._users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"last_login_at": logged_in_at}},
        )
