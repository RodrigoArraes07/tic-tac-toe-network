import os
from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import pytest
from pymongo import MongoClient
from pymongo.collection import Collection

os.environ.setdefault(
    "MONGO_URI",
    "mongodb://jogo_app:troque-esta-senha@localhost:27017/jogo_da_velha?authSource=jogo_da_velha",
)
os.environ.setdefault("MONGO_DB", "jogo_da_velha")
os.environ.setdefault("JWT_SECRET", "segredo-usado-apenas-nos-testes-automatizados")
os.environ.setdefault("JWT_EXPIRES_MINUTES", "60")

TEST_USERNAME_PREFIX = "t_"
TEST_USERNAME_SUFFIX_LENGTH = 12


@pytest.fixture
def users_collection() -> Iterator[Collection[dict[str, Any]]]:
    client: MongoClient[dict[str, Any]] = MongoClient(os.environ["MONGO_URI"])
    yield client[os.environ["MONGO_DB"]]["users"]
    client.close()


@pytest.fixture
def new_username(users_collection: Collection[dict[str, Any]]) -> Iterator[Callable[[], str]]:
    created: list[str] = []

    def _new_username() -> str:
        username = TEST_USERNAME_PREFIX + uuid4().hex[:TEST_USERNAME_SUFFIX_LENGTH]
        created.append(username)
        return username

    yield _new_username
    users_collection.delete_many({"username": {"$in": created}})
