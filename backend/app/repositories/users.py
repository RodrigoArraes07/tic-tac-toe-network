from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, UpdateOne
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

USERS_COLLECTION = "users"
POINTS_PER_WIN = 3
POINTS_PER_DRAW = 1
RANKING_INDEX = [("stats.points", DESCENDING), ("stats.wins", DESCENDING)]
RANKING_SORT = [*RANKING_INDEX, ("stats.losses", ASCENDING), ("username", ASCENDING)]
RANKING_PROJECTION = {"_id": False, "username": True, "stats": True}

type StatsIncrement = dict[str, int]


class DuplicateUsernameError(Exception):
    pass


class UserNotFoundError(Exception):
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


@dataclass(frozen=True)
class UserScore:
    username: str
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
        await self._users.create_index(RANKING_INDEX)

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

    async def list_ranking(self, limit: int) -> list[UserScore]:
        cursor = self._users.find({}, RANKING_PROJECTION).sort(RANKING_SORT).limit(limit)
        return [
            UserScore(username=document["username"], stats=UserStats(**document["stats"]))
            async for document in cursor
        ]

    async def apply_win(self, winner_id: str, loser_id: str) -> None:
        await self._increment_stats(
            {
                winner_id: {"stats.wins": 1, "stats.points": POINTS_PER_WIN},
                loser_id: {"stats.losses": 1},
            }
        )

    async def apply_draw(self, player_a_id: str, player_b_id: str) -> None:
        increment = {"stats.draws": 1, "stats.points": POINTS_PER_DRAW}
        await self._increment_stats({player_a_id: increment, player_b_id: increment})

    async def _increment_stats(self, increments: dict[str, StatsIncrement]) -> None:
        object_ids = [_to_object_id(user_id) for user_id in increments]
        # Conferido antes de gravar: sem transação, um id inexistente deixaria
        # só um dos dois jogadores atualizado.
        if None in object_ids or await self._count_existing(object_ids) != len(object_ids):
            raise UserNotFoundError
        await self._users.bulk_write(
            [
                UpdateOne({"_id": object_id}, {"$inc": increment})
                for object_id, increment in zip(object_ids, increments.values(), strict=True)
            ]
        )

    async def _count_existing(self, object_ids: list[ObjectId | None]) -> int:
        return await self._users.count_documents({"_id": {"$in": object_ids}})
