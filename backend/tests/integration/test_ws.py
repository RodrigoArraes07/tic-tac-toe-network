from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.ws import gateway
from tests.integration.ws_helpers import closed_code, create_player, send

SHORT_AUTH_TIMEOUT_SECONDS = 0.2
UNAUTHENTICATED_CODE = 4401

type UsernameFactory = Callable[[], str]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_connection_without_auth_is_closed_after_the_deadline(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(gateway, "AUTH_TIMEOUT_SECONDS", SHORT_AUTH_TIMEOUT_SECONDS)

    with client.websocket_connect("/ws") as websocket:
        code = closed_code(websocket)

    assert code == UNAUTHENTICATED_CODE


def test_auth_with_invalid_token_is_closed(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        send(websocket, "AUTH", {"token": "token-invalido"})
        code = closed_code(websocket)

    assert code == UNAUTHENTICATED_CODE


def test_first_message_other_than_auth_is_closed(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        send(websocket, "MOVE", {"match_id": "m1", "cell": 4, "seq": 0})
        code = closed_code(websocket)

    assert code == UNAUTHENTICATED_CODE


def test_valid_auth_gets_auth_ok_then_presence_snapshot(
    client: TestClient, new_username: UsernameFactory
) -> None:
    player = create_player(client, new_username())

    with client.websocket_connect("/ws") as websocket:
        auth_id = send(websocket, "AUTH", {"token": player.token})
        auth_ok = websocket.receive_json()
        snapshot = websocket.receive_json()

    assert auth_ok["type"] == "AUTH_OK"
    assert auth_ok["ref"] == auth_id
    assert auth_ok["payload"]["user"] == {"id": player.user_id, "username": player.username}
    assert auth_ok["payload"]["active_match_id"] is None
    assert snapshot["type"] == "PRESENCE_SNAPSHOT"
    assert {"username": player.username, "status": "FREE"} in snapshot["payload"]["users"]
