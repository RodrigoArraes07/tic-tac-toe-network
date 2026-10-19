from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pymongo.collection import Collection

from app.core.config import Settings
from app.main import create_app
from app.services import game_engine
from tests.integration.ws_helpers import (
    Player,
    authenticate,
    create_player,
    play,
    receive,
    receive_presence_free,
    send,
    start_match,
)

SHORT_TURN_SECONDS = 0.3
SHORT_GRACE_SECONDS = 1
WIN_MOVES = [0, 3, 1, 4, 2]
DRAW_MOVES = [0, 1, 2, 4, 3, 5, 7, 6, 8]
WIN_STATS = {"wins": 1, "losses": 0, "draws": 0, "points": 3}
LOSS_STATS = {"wins": 0, "losses": 1, "draws": 0, "points": 0}
DRAW_STATS = {"wins": 0, "losses": 0, "draws": 1, "points": 1}

type UsernameFactory = Callable[[], str]
type MongoCollection = Collection[dict[str, Any]]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def short_turn_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(game_engine, "TURN_TIMEOUT_SECONDS", SHORT_TURN_SECONDS)
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def short_grace_client() -> Iterator[TestClient]:
    settings = Settings(reconnect_grace_s=SHORT_GRACE_SECONDS)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


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
    return create_player(client, new_username()), create_player(client, new_username())


def test_line_win_ends_the_match_for_both_players(
    client: TestClient,
    players: tuple[Player, Player],
    users_collection: MongoCollection,
    matches_collection: MongoCollection,
    created_matches: list[str],
) -> None:
    x, o = players
    with client.websocket_connect("/ws") as ws_x, client.websocket_connect("/ws") as ws_o:
        authenticate(ws_x, x)
        authenticate(ws_o, o)
        match_id = start_match(ws_x, ws_o, o, created_matches)

        play(ws_x, ws_o, match_id, WIN_MOVES)

        ended_x = receive(ws_x, "MATCH_ENDED", match_id=match_id)["payload"]
        ended_o = receive(ws_o, "MATCH_ENDED", match_id=match_id)["payload"]
        receive_presence_free(ws_x, x.username, o.username)

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
        authenticate(ws_x, x)
        authenticate(ws_o, o)
        match_id = start_match(ws_x, ws_o, o, created_matches)

        play(ws_x, ws_o, match_id, DRAW_MOVES)

        ended_x = receive(ws_x, "MATCH_ENDED", match_id=match_id)["payload"]
        ended_o = receive(ws_o, "MATCH_ENDED", match_id=match_id)["payload"]
        receive_presence_free(ws_x, x.username, o.username)

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
        authenticate(ws_x, x)
        authenticate(ws_o, o)
        match_id = start_match(ws_x, ws_o, o, created_matches)

        forfeit_id = send(ws_o, "FORFEIT", {"match_id": match_id})

        ended_x = receive(ws_x, "MATCH_ENDED", match_id=match_id)
        ended_o = receive(ws_o, "MATCH_ENDED", match_id=match_id)
        receive_presence_free(ws_o, x.username, o.username)
        send(ws_o, "FORFEIT", {"match_id": match_id})
        after_end = receive(ws_o, "ERROR")["payload"]

    assert (ended_x["payload"]["result"], ended_o["payload"]["result"]) == ("WIN", "LOSS")
    assert ended_x["payload"]["reason"] == "FORFEIT"
    assert ended_x["payload"]["winning_line"] is None
    assert ended_o["ref"] == forfeit_id
    assert after_end["code"] == "INVALID_STATE"
    assert _stats(users_collection, x) == WIN_STATS
    assert _stats(users_collection, o) == LOSS_STATS
    stored = _stored_match(matches_collection, match_id)
    assert (stored["winner_id"], stored["reason"]) == (x.user_id, "FORFEIT")


def test_disconnect_without_return_gives_the_win_to_the_player_who_stayed(
    short_grace_client: TestClient,
    new_username: UsernameFactory,
    users_collection: MongoCollection,
    matches_collection: MongoCollection,
    created_matches: list[str],
) -> None:
    x = create_player(short_grace_client, new_username())
    o = create_player(short_grace_client, new_username())
    with short_grace_client.websocket_connect("/ws") as ws_x:
        authenticate(ws_x, x)
        with short_grace_client.websocket_connect("/ws") as ws_o:
            authenticate(ws_o, o)
            match_id = start_match(ws_x, ws_o, o, created_matches)

        away = receive(ws_x, "OPPONENT_DISCONNECTED", match_id=match_id)["payload"]
        ended_x = receive(ws_x, "MATCH_ENDED", match_id=match_id)["payload"]
        receive_presence_free(ws_x, x.username)

    assert away["grace_seconds"] == SHORT_GRACE_SECONDS
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
    x = create_player(short_turn_client, new_username())
    o = create_player(short_turn_client, new_username())
    with (
        short_turn_client.websocket_connect("/ws") as ws_x,
        short_turn_client.websocket_connect("/ws") as ws_o,
    ):
        authenticate(ws_x, x)
        authenticate(ws_o, o)
        match_id = start_match(ws_x, ws_o, o, created_matches)

        ended_x = receive(ws_x, "MATCH_ENDED", match_id=match_id)["payload"]
        ended_o = receive(ws_o, "MATCH_ENDED", match_id=match_id)["payload"]
        receive_presence_free(ws_o, x.username, o.username)

    assert (ended_x["result"], ended_o["result"]) == ("LOSS", "WIN")
    assert ended_x["reason"] == ended_o["reason"] == "TIMEOUT"
    assert _stats(users_collection, x) == LOSS_STATS
    assert _stats(users_collection, o) == WIN_STATS
    stored = _stored_match(matches_collection, match_id)
    assert (stored["winner_id"], stored["reason"]) == (o.user_id, "TIMEOUT")


def test_move_with_old_seq_is_rejected_as_stale_state(
    client: TestClient,
    players: tuple[Player, Player],
    created_matches: list[str],
) -> None:
    x, o = players
    with client.websocket_connect("/ws") as ws_x, client.websocket_connect("/ws") as ws_o:
        authenticate(ws_x, x)
        authenticate(ws_o, o)
        match_id = start_match(ws_x, ws_o, o, created_matches)
        play(ws_x, ws_o, match_id, [4])

        stale_id = send(ws_x, "MOVE", {"match_id": match_id, "cell": 0, "seq": 0})
        error = receive(ws_x, "ERROR")
        resent = receive(ws_x, "MATCH_STATE")
        send(ws_o, "MOVE", {"match_id": match_id, "cell": 8, "seq": 1})
        next_state_o = receive(ws_o, "MATCH_STATE")

    assert error["ref"] == stale_id
    assert error["payload"]["code"] == "STALE_STATE"
    assert resent["payload"]["seq"] == 1
    assert resent["payload"]["board"] == [None, None, None, None, "X", None, None, None, None]
    assert next_state_o["payload"]["seq"] == 2
    assert next_state_o["payload"]["board"] == [None, None, None, None, "X", None, None, None, "O"]


def test_match_started_names_the_opponent_by_username(
    client: TestClient, players: tuple[Player, Player], created_matches: list[str]
) -> None:
    x, o = players
    with client.websocket_connect("/ws") as ws_x, client.websocket_connect("/ws") as ws_o:
        authenticate(ws_x, x)
        authenticate(ws_o, o)
        send(ws_x, "INVITE_SEND", {"to_username": o.username})
        match_id = receive(ws_o, "INVITE_RECEIVED")["payload"]["match_id"]
        created_matches.append(match_id)
        send(ws_o, "INVITE_RESPOND", {"match_id": match_id, "accept": True})
        started_x = receive(ws_x, "MATCH_STARTED", match_id=match_id)["payload"]
        started_o = receive(ws_o, "MATCH_STARTED", match_id=match_id)["payload"]

    assert (started_x["you_are"], started_x["opponent"]) == ("X", o.username)
    assert (started_o["you_are"], started_o["opponent"]) == ("O", x.username)
