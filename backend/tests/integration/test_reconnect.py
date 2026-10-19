import time
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.core.config import Settings
from app.main import create_app
from app.services import game_engine
from tests.integration.ws_helpers import (
    Message,
    authenticate,
    closed_code,
    create_player,
    play,
    receive,
    send,
    start_match,
)

GRACE_SECONDS = 5
SHORT_TURN_SECONDS = 0.5
TURN_GRACE_SECONDS = 3
WAIT_PAST_TURN_S = SHORT_TURN_SECONDS * 3
SESSION_REPLACED_CODE = 4001
PRESENCE_TYPES = {"PRESENCE_UPDATE", "PRESENCE_SNAPSHOT"}

type UsernameFactory = Callable[[], str]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings(reconnect_grace_s=GRACE_SECONDS))) as test_client:
        yield test_client


@pytest.fixture
def short_turn_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(game_engine, "TURN_TIMEOUT_SECONDS", SHORT_TURN_SECONDS)
    settings = Settings(reconnect_grace_s=TURN_GRACE_SECONDS)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _next_non_presence(ws: WebSocketTestSession) -> Message:
    while True:
        message = ws.receive_json()
        if message["type"] not in PRESENCE_TYPES:
            return message


def _resume(ws: WebSocketTestSession, token: str, match_id: str) -> Message:
    send(ws, "AUTH", {"token": token})
    auth_ok = receive(ws, "AUTH_OK")["payload"]
    assert auth_ok["active_match_id"] == match_id
    send(ws, "MATCH_SYNC", {"match_id": match_id})
    return receive(ws, "MATCH_STATE")["payload"]


def test_player_who_returns_in_time_continues_the_match(
    client: TestClient, new_username: UsernameFactory, created_matches: list[str]
) -> None:
    x = create_player(client, new_username())
    o = create_player(client, new_username())
    with client.websocket_connect("/ws") as ws_x:
        authenticate(ws_x, x)
        with client.websocket_connect("/ws") as ws_o:
            authenticate(ws_o, o)
            match_id = start_match(ws_x, ws_o, o, created_matches)
            play(ws_x, ws_o, match_id, [4])

        away = _next_non_presence(ws_x)
        with client.websocket_connect("/ws") as ws_o_again:
            synced = _resume(ws_o_again, o.token, match_id)
            back = _next_non_presence(ws_x)
            send(ws_o_again, "MOVE", {"match_id": match_id, "cell": 0, "seq": 1})
            state_x = receive(ws_x, "MATCH_STATE", seq=2)["payload"]

    assert away["type"] == "OPPONENT_DISCONNECTED"
    assert away["payload"] == {"match_id": match_id, "grace_seconds": GRACE_SECONDS}
    assert back["type"] == "OPPONENT_RECONNECTED"
    assert back["payload"] == {"match_id": match_id}
    assert (synced["seq"], synced["you_are"], synced["board"][4]) == (1, "O", "X")
    assert state_x["board"][0] == "O"


def test_turn_does_not_expire_while_the_player_is_away(
    short_turn_client: TestClient, new_username: UsernameFactory, created_matches: list[str]
) -> None:
    client = short_turn_client
    x = create_player(client, new_username())
    o = create_player(client, new_username())
    with client.websocket_connect("/ws") as ws_o:
        authenticate(ws_o, o)
        with client.websocket_connect("/ws") as ws_x:
            authenticate(ws_x, x)
            match_id = start_match(ws_x, ws_o, o, created_matches)

        away = _next_non_presence(ws_o)
        time.sleep(WAIT_PAST_TURN_S)
        with client.websocket_connect("/ws") as ws_x_again:
            synced = _resume(ws_x_again, x.token, match_id)
            back = _next_non_presence(ws_o)
            send(ws_x_again, "MOVE", {"match_id": match_id, "cell": 4, "seq": 0})
            state_o = receive(ws_o, "MATCH_STATE", seq=1)["payload"]

    assert away["type"] == "OPPONENT_DISCONNECTED"
    assert back["type"] == "OPPONENT_RECONNECTED"
    assert (synced["turn"], synced["seq"]) == ("X", 0)
    assert state_o["board"][4] == "X"


def test_second_tab_does_not_open_a_reconnection_window(
    client: TestClient, new_username: UsernameFactory, created_matches: list[str]
) -> None:
    a = create_player(client, new_username())
    b = create_player(client, new_username())
    with client.websocket_connect("/ws") as ws_b, client.websocket_connect("/ws") as ws_a1:
        authenticate(ws_b, b)
        authenticate(ws_a1, a)
        match_id = start_match(ws_a1, ws_b, b, created_matches)
        with client.websocket_connect("/ws") as ws_a2:
            authenticate(ws_a2, a)
            old_connection = closed_code(ws_a1)
            send(ws_a2, "MOVE", {"match_id": match_id, "cell": 4, "seq": 0})
            next_for_b = _next_non_presence(ws_b)

    assert old_connection == SESSION_REPLACED_CODE
    assert next_for_b["type"] == "MATCH_STATE"
    assert next_for_b["payload"]["seq"] == 1


def test_returning_player_is_shown_in_match(
    client: TestClient, new_username: UsernameFactory, created_matches: list[str]
) -> None:
    x = create_player(client, new_username())
    o = create_player(client, new_username())
    with client.websocket_connect("/ws") as ws_x:
        authenticate(ws_x, x)
        with client.websocket_connect("/ws") as ws_o:
            authenticate(ws_o, o)
            match_id = start_match(ws_x, ws_o, o, created_matches)

        receive(ws_x, "OPPONENT_DISCONNECTED", match_id=match_id)
        with client.websocket_connect("/ws") as ws_o_again:
            _resume(ws_o_again, o.token, match_id)
            statuses = _presence_until_reconnected(ws_x, o.username)

    # Na volta a conexão nova anuncia FREE e o servidor corrige para IN_MATCH.
    assert statuses[-1] == "IN_MATCH"


def _presence_until_reconnected(ws: WebSocketTestSession, username: str) -> list[str]:
    statuses: list[str] = []
    reconnected = False
    while not (reconnected and statuses and statuses[-1] == "IN_MATCH"):
        message = ws.receive_json()
        if message["type"] == "OPPONENT_RECONNECTED":
            reconnected = True
        elif message["type"] == "PRESENCE_UPDATE" and message["payload"]["username"] == username:
            statuses.append(message["payload"]["status"])
    return statuses
