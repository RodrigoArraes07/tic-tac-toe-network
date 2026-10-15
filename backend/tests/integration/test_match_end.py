from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo.collection import Collection
from starlette.testclient import WebSocketTestSession

from app.main import create_app
from app.services import game_engine

PASSWORD = "senha-correta-123"
SHORT_TURN_SECONDS = 0.3
WIN_MOVES = [0, 3, 1, 4, 2]
DRAW_MOVES = [0, 1, 2, 4, 3, 5, 7, 6, 8]
WIN_STATS = {"wins": 1, "losses": 0, "draws": 0, "points": 3}
LOSS_STATS = {"wins": 0, "losses": 1, "draws": 0, "points": 0}
DRAW_STATS = {"wins": 0, "losses": 0, "draws": 1, "points": 1}

type Message = dict[str, Any]
type UsernameFactory = Callable[[], str]
type MongoCollection = Collection[dict[str, Any]]


@dataclass(frozen=True)
class Player:
    username: str
    user_id: str
    token: str


@pytest.fixture
def matches_collection(users_collection: MongoCollection) -> Iterator[MongoCollection]:
    yield users_collection.database["matches"]


@pytest.fixture
def created_matches(matches_collection: MongoCollection) -> Iterator[list[str]]:
    match_ids: list[str] = []
    yield match_ids
    matches_collection.delete_many({"_id": {"$in": match_ids}})


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def short_turn_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(game_engine, "TURN_TIMEOUT_SECONDS", SHORT_TURN_SECONDS)
    with TestClient(create_app()) as test_client:
        yield test_client


def _create_player(client: TestClient, username: str) -> Player:
    credentials = {"username": username, "password": PASSWORD}
    user_id = client.post("/api/auth/register", json=credentials).json()["id"]
    token = client.post("/api/auth/login", json=credentials).json()["access_token"]
    return Player(username=username, user_id=user_id, token=token)


def _send(ws: WebSocketTestSession, message_type: str, payload: dict[str, Any]) -> str:
    message_id = str(uuid4())
    ws.send_json({"type": message_type, "id": message_id, "ref": None, "payload": payload})
    return message_id


def _receive(ws: WebSocketTestSession, message_type: str, **expected: Any) -> Message:
    while True:
        message = ws.receive_json()
        payload = message["payload"]
        if message["type"] == message_type and all(
            payload.get(k) == v for k, v in expected.items()
        ):
            return message


def _receive_presence_free(ws: WebSocketTestSession, *usernames: str) -> None:
    pending = set(usernames)
    while pending:
        pending.discard(_receive(ws, "PRESENCE_UPDATE", status="FREE")["payload"]["username"])


def _authenticate(ws: WebSocketTestSession, player: Player) -> None:
    _send(ws, "AUTH", {"token": player.token})
    _receive(ws, "AUTH_OK")


def _start_match(
    ws_x: WebSocketTestSession,
    ws_o: WebSocketTestSession,
    player_o: Player,
    created_matches: list[str],
) -> str:
    _send(ws_x, "INVITE_SEND", {"to_username": player_o.username})
    match_id = _receive(ws_o, "INVITE_RECEIVED")["payload"]["match_id"]
    created_matches.append(match_id)
    _send(ws_o, "INVITE_RESPOND", {"match_id": match_id, "accept": True})
    for ws in (ws_x, ws_o):
        started = _receive(ws, "MATCH_STARTED", match_id=match_id)
        assert started["payload"]["seq"] == 0
    return match_id


def _play(
    ws_x: WebSocketTestSession, ws_o: WebSocketTestSession, match_id: str, cells: list[int]
) -> None:
    for seq, cell in enumerate(cells):
        mover = ws_x if seq % 2 == 0 else ws_o
        _send(mover, "MOVE", {"match_id": match_id, "cell": cell, "seq": seq})
        for ws in (ws_x, ws_o):
            state = _receive(ws, "MATCH_STATE", seq=seq + 1)
            assert state["payload"]["last_move"]["cell"] == cell


def _stats(users_collection: MongoCollection, player: Player) -> Any:
    document = users_collection.find_one({"username": player.username})
    assert document is not None
    return document["stats"]


def _stored_match(matches_collection: MongoCollection, match_id: str) -> Any:
    document = matches_collection.find_one({"_id": match_id})
    assert document is not None
    return document


@pytest.fixture
def players(client: TestClient, new_username: UsernameFactory) -> tuple[Player, Player]:
    return _create_player(client, new_username()), _create_player(client, new_username())


def test_line_win_ends_the_match_for_both_players(
    client: TestClient,
    players: tuple[Player, Player],
    users_collection: MongoCollection,
    matches_collection: MongoCollection,
    created_matches: list[str],
) -> None:
    x, o = players
    with client.websocket_connect("/ws") as ws_x, client.websocket_connect("/ws") as ws_o:
        _authenticate(ws_x, x)
        _authenticate(ws_o, o)
        match_id = _start_match(ws_x, ws_o, o, created_matches)

        _play(ws_x, ws_o, match_id, WIN_MOVES)

        ended_x = _receive(ws_x, "MATCH_ENDED", match_id=match_id)["payload"]
        ended_o = _receive(ws_o, "MATCH_ENDED", match_id=match_id)["payload"]
        _receive_presence_free(ws_x, x.username, o.username)

    assert (ended_x["result"], ended_o["result"]) == ("WIN", "LOSS")
    assert ended_x["reason"] == ended_o["reason"] == "LINE"
    assert ended_x["winning_line"] == [0, 1, 2]
    assert ended_x["board"] == ["X", "X", "X", "O", "O", None, None, None, None]
    assert _stats(users_collection, x) == WIN_STATS
    assert _stats(users_collection, o) == LOSS_STATS
    stored = _stored_match(matches_collection, match_id)
    assert (stored["winner_id"], stored["reason"]) == (x.user_id, "LINE")
    assert (stored["player_x_id"], stored["player_o_id"]) == (x.user_id, o.user_id)


def test_full_board_ends_in_a_draw(
    client: TestClient,
    players: tuple[Player, Player],
    users_collection: MongoCollection,
    matches_collection: MongoCollection,
    created_matches: list[str],
) -> None:
    x, o = players
    with client.websocket_connect("/ws") as ws_x, client.websocket_connect("/ws") as ws_o:
        _authenticate(ws_x, x)
        _authenticate(ws_o, o)
        match_id = _start_match(ws_x, ws_o, o, created_matches)

        _play(ws_x, ws_o, match_id, DRAW_MOVES)

        ended_x = _receive(ws_x, "MATCH_ENDED", match_id=match_id)["payload"]
        ended_o = _receive(ws_o, "MATCH_ENDED", match_id=match_id)["payload"]
        _receive_presence_free(ws_x, x.username, o.username)

    assert (ended_x["result"], ended_o["result"]) == ("DRAW", "DRAW")
    assert ended_x["reason"] == "DRAW"
    assert ended_x["winning_line"] is None
    assert _stats(users_collection, x) == DRAW_STATS
    assert _stats(users_collection, o) == DRAW_STATS
    stored = _stored_match(matches_collection, match_id)
    assert (stored["winner_id"], stored["reason"]) == (None, "DRAW")


def test_forfeit_gives_the_win_to_the_opponent(
    client: TestClient,
    players: tuple[Player, Player],
    users_collection: MongoCollection,
    matches_collection: MongoCollection,
    created_matches: list[str],
) -> None:
    x, o = players
    with client.websocket_connect("/ws") as ws_x, client.websocket_connect("/ws") as ws_o:
        _authenticate(ws_x, x)
        _authenticate(ws_o, o)
        match_id = _start_match(ws_x, ws_o, o, created_matches)

        forfeit_id = _send(ws_o, "FORFEIT", {"match_id": match_id})

        ended_x = _receive(ws_x, "MATCH_ENDED", match_id=match_id)
        ended_o = _receive(ws_o, "MATCH_ENDED", match_id=match_id)
        _receive_presence_free(ws_o, x.username, o.username)
        _send(ws_o, "FORFEIT", {"match_id": match_id})
        after_end = _receive(ws_o, "ERROR")["payload"]

    assert (ended_x["payload"]["result"], ended_o["payload"]["result"]) == ("WIN", "LOSS")
    assert ended_x["payload"]["reason"] == "FORFEIT"
    assert ended_x["payload"]["winning_line"] is None
    assert ended_o["ref"] == forfeit_id
    assert after_end["code"] == "INVALID_STATE"
    assert _stats(users_collection, x) == WIN_STATS
    assert _stats(users_collection, o) == LOSS_STATS
    stored = _stored_match(matches_collection, match_id)
    assert (stored["winner_id"], stored["reason"]) == (x.user_id, "FORFEIT")


def test_disconnect_gives_the_win_to_the_player_who_stayed(
    client: TestClient,
    players: tuple[Player, Player],
    users_collection: MongoCollection,
    matches_collection: MongoCollection,
    created_matches: list[str],
) -> None:
    x, o = players
    with client.websocket_connect("/ws") as ws_x:
        _authenticate(ws_x, x)
        with client.websocket_connect("/ws") as ws_o:
            _authenticate(ws_o, o)
            match_id = _start_match(ws_x, ws_o, o, created_matches)

        ended_x = _receive(ws_x, "MATCH_ENDED", match_id=match_id)["payload"]
        _receive_presence_free(ws_x, x.username)

    assert ended_x["result"] == "WIN"
    assert ended_x["reason"] == "DISCONNECT"
    assert _stats(users_collection, x) == WIN_STATS
    assert _stats(users_collection, o) == LOSS_STATS
    stored = _stored_match(matches_collection, match_id)
    assert (stored["winner_id"], stored["reason"]) == (x.user_id, "DISCONNECT")


def test_turn_timeout_ends_the_match_and_notifies_both_players(
    short_turn_client: TestClient,
    new_username: UsernameFactory,
    users_collection: MongoCollection,
    matches_collection: MongoCollection,
    created_matches: list[str],
) -> None:
    x = _create_player(short_turn_client, new_username())
    o = _create_player(short_turn_client, new_username())
    with (
        short_turn_client.websocket_connect("/ws") as ws_x,
        short_turn_client.websocket_connect("/ws") as ws_o,
    ):
        _authenticate(ws_x, x)
        _authenticate(ws_o, o)
        match_id = _start_match(ws_x, ws_o, o, created_matches)

        ended_x = _receive(ws_x, "MATCH_ENDED", match_id=match_id)["payload"]
        ended_o = _receive(ws_o, "MATCH_ENDED", match_id=match_id)["payload"]
        _receive_presence_free(ws_o, x.username, o.username)

    assert (ended_x["result"], ended_o["result"]) == ("LOSS", "WIN")
    assert ended_x["reason"] == ended_o["reason"] == "FORFEIT"
    assert _stats(users_collection, x) == LOSS_STATS
    assert _stats(users_collection, o) == WIN_STATS
    stored = _stored_match(matches_collection, match_id)
    assert (stored["winner_id"], stored["reason"]) == (o.user_id, "FORFEIT")


def test_move_with_old_seq_is_rejected_as_stale_state(
    client: TestClient,
    players: tuple[Player, Player],
    created_matches: list[str],
) -> None:
    x, o = players
    with client.websocket_connect("/ws") as ws_x, client.websocket_connect("/ws") as ws_o:
        _authenticate(ws_x, x)
        _authenticate(ws_o, o)
        match_id = _start_match(ws_x, ws_o, o, created_matches)
        _play(ws_x, ws_o, match_id, [4])

        stale_id = _send(ws_x, "MOVE", {"match_id": match_id, "cell": 0, "seq": 0})
        error = _receive(ws_x, "ERROR")
        resent = _receive(ws_x, "MATCH_STATE")
        _send(ws_o, "MOVE", {"match_id": match_id, "cell": 8, "seq": 1})
        next_state_o = _receive(ws_o, "MATCH_STATE")

    assert error["ref"] == stale_id
    assert error["payload"]["code"] == "STALE_STATE"
    assert resent["payload"]["seq"] == 1
    assert resent["payload"]["board"] == [None, None, None, None, "X", None, None, None, None]
    assert next_state_o["payload"]["seq"] == 2
    assert next_state_o["payload"]["board"] == [None, None, None, None, "X", None, None, None, "O"]
