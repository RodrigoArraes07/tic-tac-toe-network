import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.main import create_app
from tests.integration.ws_helpers import (
    Player,
    authenticate,
    closed_code,
    create_player,
    play,
    receive,
    send,
    start_match,
)

SLOW_RATE_PER_SECOND = 0.5
SMALL_BURST = 3
WARNINGS_BEFORE_CLOSE = 3
PROTOCOL_VIOLATION_CODE = 4400
MESSAGE_TOO_BIG_CODE = 1009
# Cabe o AUTH com o JWT (algumas centenas de bytes), mas não a mensagem de teste.
SMALL_MESSAGE_LIMIT = 1024
WIN_MOVES = [0, 3, 1, 4, 2]
VALID_ORIGIN = "https://localhost"
FOREIGN_ORIGIN = "https://evil.example"

type UsernameFactory = Callable[[], str]
type ClientFactory = Callable[..., AbstractContextManager[TestClient]]


@pytest.fixture
def make_client() -> ClientFactory:
    def factory(**overrides: Any) -> AbstractContextManager[TestClient]:
        return TestClient(create_app(Settings(**overrides)))

    return factory


@pytest.fixture
def client(make_client: ClientFactory) -> Iterator[TestClient]:
    with make_client() as test_client:
        yield test_client


def _json_events(output: str, event_type: str) -> list[dict[str, Any]]:
    events = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    return [event for event in events if event["type"] == event_type]


def _connect_and_auth(client: TestClient, player: Player, **headers: str) -> str:
    with client.websocket_connect("/ws", headers=headers) as websocket:
        send(websocket, "AUTH", {"token": player.token})
        return receive(websocket, "AUTH_OK")["type"]


def test_burst_above_the_limit_is_warned_then_closed(
    make_client: ClientFactory,
    new_username: UsernameFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = {"ws_rate_per_second": SLOW_RATE_PER_SECOND, "ws_rate_burst": SMALL_BURST}
    with make_client(**settings) as client:
        player = create_player(client, new_username())
        with client.websocket_connect("/ws") as websocket:
            authenticate(websocket, player)
            message_ids = [
                send(websocket, "PING", {}) for _ in range(SMALL_BURST + WARNINGS_BEFORE_CLOSE + 1)
            ]
            errors = [
                receive(websocket, "ERROR") for _ in range(SMALL_BURST + WARNINGS_BEFORE_CLOSE)
            ]
            code = closed_code(websocket)

    output = capsys.readouterr().out
    actions = [event["details"]["action"] for event in _json_events(output, "ws.rate_limited")]
    assert [e["payload"]["code"] for e in errors] == ["UNKNOWN_TYPE"] * SMALL_BURST + [
        "RATE_LIMITED"
    ] * WARNINGS_BEFORE_CLOSE
    assert [e["ref"] for e in errors] == message_ids[: SMALL_BURST + WARNINGS_BEFORE_CLOSE]
    assert code == PROTOCOL_VIOLATION_CODE
    assert actions == ["warned"] * WARNINGS_BEFORE_CLOSE + ["closed"]


def test_normal_match_is_not_rate_limited(
    client: TestClient, new_username: UsernameFactory, created_matches: list[str]
) -> None:
    x = create_player(client, new_username())
    o = create_player(client, new_username())
    with client.websocket_connect("/ws") as ws_x, client.websocket_connect("/ws") as ws_o:
        authenticate(ws_x, x)
        authenticate(ws_o, o)
        match_id = start_match(ws_x, ws_o, o, created_matches)

        play(ws_x, ws_o, match_id, WIN_MOVES)

        ended_x = receive(ws_x, "MATCH_ENDED", match_id=match_id)["payload"]
        ended_o = receive(ws_o, "MATCH_ENDED", match_id=match_id)["payload"]

    assert (ended_x["result"], ended_o["result"]) == ("WIN", "LOSS")


def test_foreign_origin_is_rejected_in_the_handshake(
    make_client: ClientFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    # O app nasce depois do capsys, para o log JSON ir para a saída capturada.
    with (
        make_client() as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws", headers={"origin": FOREIGN_ORIGIN}),
    ):
        pass

    rejected = _json_events(capsys.readouterr().out, "security.origin_rejected")
    assert len(rejected) == 1
    assert rejected[0]["details"]["origin"] == FOREIGN_ORIGIN
    assert "ip" in rejected[0]["details"]


def test_valid_or_missing_origin_is_accepted(
    client: TestClient, new_username: UsernameFactory
) -> None:
    player = create_player(client, new_username())

    with_origin = _connect_and_auth(client, player, origin=VALID_ORIGIN)
    without_origin = _connect_and_auth(client, player)

    assert with_origin == without_origin == "AUTH_OK"


def test_configured_origin_is_normalized(
    make_client: ClientFactory, new_username: UsernameFactory
) -> None:
    with make_client(allowed_origins=f"{VALID_ORIGIN}/") as client:
        player = create_player(client, new_username())

        accepted = _connect_and_auth(client, player, origin=VALID_ORIGIN)

    assert accepted == "AUTH_OK"


def test_message_above_the_size_limit_closes_the_connection(
    make_client: ClientFactory, new_username: UsernameFactory
) -> None:
    with make_client(ws_max_message_bytes=SMALL_MESSAGE_LIMIT) as client:
        player = create_player(client, new_username())
        with client.websocket_connect("/ws") as websocket:
            authenticate(websocket, player)
            send(websocket, "MATCH_SYNC", {"match_id": "x" * (SMALL_MESSAGE_LIMIT + 50)})
            code = closed_code(websocket)

    assert code == MESSAGE_TOO_BIG_CODE
