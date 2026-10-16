import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo.collection import Collection

from app.core.config import Settings
from app.main import create_app
from app.repositories.events import EventRepository
from tests.integration.ws_helpers import authenticate, create_player

DRAIN_BATCH_SIZE = 50
TEST_EVENT_PREFIX = "teste."
NORMAL_CLOSE_CODE = 1000

type MongoCollection = Collection[dict[str, Any]]
type ClientFactory = Callable[[], AbstractContextManager[TestClient]]

test_logger = logging.getLogger("tests.audit")


@pytest.fixture
def events_collection(users_collection: MongoCollection) -> MongoCollection:
    return users_collection.database["events"]


@pytest.fixture
def created_user_ids() -> list[str]:
    return []


@pytest.fixture
def audit_client(
    monkeypatch: pytest.MonkeyPatch,
    events_collection: MongoCollection,
    created_user_ids: list[str],
) -> Iterator[ClientFactory]:
    inserted_ids: list[Any] = []
    original_insert = EventRepository.insert

    async def recording_insert(self: EventRepository, event: dict[str, Any]) -> None:
        await original_insert(self, event)
        inserted_ids.append(event["_id"])

    monkeypatch.setattr(EventRepository, "insert", recording_insert)

    def factory() -> AbstractContextManager[TestClient]:
        return TestClient(create_app(Settings(audit_enabled=True)))

    yield factory
    events_collection.delete_many(
        {
            "$or": [
                {"_id": {"$in": inserted_ids}},
                {"type": {"$regex": f"^{TEST_EVENT_PREFIX}"}},
                {"user_id": {"$in": created_user_ids}},
            ]
        }
    )


def _marker() -> str:
    return uuid4().hex


def test_logged_event_is_saved_with_the_section_8_fields(
    audit_client: ClientFactory, events_collection: MongoCollection
) -> None:
    marker = _marker()

    with audit_client():
        details = {"user_id": marker, "match_id": "partida-1", "detalhe": "valor"}
        test_logger.info("teste.auditoria", extra={"details": details})

    stored = events_collection.find_one({"type": "teste.auditoria", "user_id": marker})
    assert stored is not None
    assert isinstance(stored["ts"], datetime)
    assert stored["level"] == "INFO"
    assert stored["match_id"] == "partida-1"
    assert stored["details"] == {"detalhe": "valor"}


def test_real_application_events_are_saved(
    audit_client: ClientFactory,
    events_collection: MongoCollection,
    new_username: Callable[[], str],
    created_user_ids: list[str],
) -> None:
    with audit_client() as client:
        player = create_player(client, new_username())
        created_user_ids.append(player.user_id)
        with client.websocket_connect("/ws") as websocket:
            authenticate(websocket, player)

    registered = events_collection.find_one(
        {"type": "user.registered", "details.username": player.username}
    )
    connected = events_collection.find_one({"type": "user.connected", "user_id": player.user_id})
    disconnected = events_collection.find_one(
        {"type": "user.disconnected", "user_id": player.user_id}
    )
    assert registered is not None
    assert connected is not None
    assert connected["details"]["username"] == player.username
    assert {"ip", "port"} <= connected["details"].keys()
    assert disconnected is not None
    assert disconnected["details"]["close_code"] == NORMAL_CLOSE_CODE
    assert disconnected["details"]["duration_s"] >= 0


def test_access_logs_and_records_without_details_are_not_saved(
    audit_client: ClientFactory, events_collection: MongoCollection
) -> None:
    marker = _marker()

    with audit_client():
        access = logging.getLogger("uvicorn.access")
        access.info("teste.acesso", extra={"details": {"user_id": marker}})
        test_logger.info("teste.sem_details")
        test_logger.info("teste.controle", extra={"details": {"user_id": marker}})

    saved_types = {doc["type"] for doc in events_collection.find({"user_id": marker})}
    assert saved_types == {"teste.controle"}
    assert events_collection.count_documents({"type": "teste.sem_details"}) == 0


def test_sensitive_fields_are_removed_before_saving(
    audit_client: ClientFactory, events_collection: MongoCollection
) -> None:
    marker = _marker()
    details = {
        "user_id": marker,
        "username": "fulano",
        "password": "senha",
        "password_hash": "$argon2id$hash",
        "token": "jwt",
        "access_token": "jwt",
        "Authorization": "Bearer jwt",
        "Secret": "segredo",
        "cookie": "sessao=1",
        "nested": {"token": "jwt", "keep": 1},
        "items": [{"password": "senha", "ok": True}],
    }

    with audit_client():
        test_logger.warning("teste.sensivel", extra={"details": details})

    stored = events_collection.find_one({"type": "teste.sensivel", "user_id": marker})
    assert stored is not None
    assert stored["level"] == "WARNING"
    assert stored["details"] == {
        "username": "fulano",
        "nested": {"keep": 1},
        "items": [{"ok": True}],
    }


def test_queue_is_drained_on_shutdown(
    audit_client: ClientFactory, events_collection: MongoCollection
) -> None:
    marker = _marker()

    with audit_client():
        for number in range(DRAIN_BATCH_SIZE):
            details = {"user_id": marker, "number": number}
            test_logger.info("teste.drenagem", extra={"details": details})

    saved = events_collection.count_documents({"type": "teste.drenagem", "user_id": marker})
    assert saved == DRAIN_BATCH_SIZE
