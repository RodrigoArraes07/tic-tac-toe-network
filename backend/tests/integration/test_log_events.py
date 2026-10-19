import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.integration.ws_helpers import (
    Player,
    authenticate,
    create_player,
    receive,
    send,
    start_match,
)

CONFIGURED_PORT = 8000
SHORT_INVITE_TIMEOUT_S = 1
WRONG_PASSWORD = "senha-errada-123"

type UsernameFactory = Callable[[], str]
type Details = dict[str, Any]


def _details(output: str, event_type: str) -> list[Details]:
    events = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    return [event["details"] for event in events if event["type"] == event_type]


def _invite_fields(details: Details, from_player: Player, to_player: Player) -> Details:
    keys = ("from_user_id", "from_username", "to_user_id", "to_username")
    assert {key: details[key] for key in keys} == {
        "from_user_id": from_player.user_id,
        "from_username": from_player.username,
        "to_user_id": to_player.user_id,
        "to_username": to_player.username,
    }
    return details


def test_server_started_logs_the_configured_port(capsys: pytest.CaptureFixture[str]) -> None:
    with TestClient(create_app()):
        pass

    started = _details(capsys.readouterr().out, "server.started")
    assert len(started) == 1
    assert started[0]["port"] == CONFIGURED_PORT
    assert {"version", "db"} <= started[0].keys()


def test_registration_and_login_events_carry_the_user_id(
    capsys: pytest.CaptureFixture[str], new_username: UsernameFactory
) -> None:
    with TestClient(create_app()) as client:
        player = create_player(client, new_username())
        wrong = {"username": player.username, "password": WRONG_PASSWORD}
        client.post("/api/auth/login", json=wrong)
        unknown = {"username": new_username(), "password": WRONG_PASSWORD}
        client.post("/api/auth/login", json=unknown)

    output = capsys.readouterr().out
    registered = _details(output, "user.registered")
    logged_in = _details(output, "user.login")
    failed = _details(output, "user.login_failed")
    assert [d["user_id"] for d in registered] == [player.user_id]
    assert [d["user_id"] for d in logged_in] == [player.user_id]
    assert [d["user_id"] for d in failed] == [player.user_id, None]


def test_invite_events_carry_the_match_and_both_players(
    capsys: pytest.CaptureFixture[str],
    new_username: UsernameFactory,
    created_matches: list[str],
) -> None:
    settings = Settings(invite_timeout_s=SHORT_INVITE_TIMEOUT_S)
    with TestClient(create_app(settings)) as client:
        a = create_player(client, new_username())
        b = create_player(client, new_username())
        with client.websocket_connect("/ws") as ws_a, client.websocket_connect("/ws") as ws_b:
            authenticate(ws_a, a)
            authenticate(ws_b, b)
            match_ids = []
            for action in ("reject", "cancel", "expire"):
                send(ws_a, "INVITE_SEND", {"to_username": b.username})
                match_id = receive(ws_b, "INVITE_RECEIVED")["payload"]["match_id"]
                match_ids.append(match_id)
                if action == "reject":
                    send(ws_b, "INVITE_RESPOND", {"match_id": match_id, "accept": False})
                elif action == "cancel":
                    send(ws_a, "INVITE_CANCEL", {"match_id": match_id})
                receive(ws_a, "INVITE_RESULT", match_id=match_id)
            accepted_id = start_match(ws_a, ws_b, b, created_matches)

    output = capsys.readouterr().out
    sent = [_invite_fields(d, a, b) for d in _details(output, "invite.sent")]
    rejected = _invite_fields(_details(output, "invite.rejected")[0], a, b)
    cancelled = _invite_fields(_details(output, "invite.cancelled")[0], a, b)
    expired = _invite_fields(_details(output, "invite.expired")[0], a, b)
    accepted = _invite_fields(_details(output, "invite.accepted")[0], a, b)
    assert [d["match_id"] for d in sent] == [*match_ids, accepted_id]
    assert all(d["user_id"] == a.user_id for d in sent)
    assert (rejected["match_id"], rejected["user_id"]) == (match_ids[0], b.user_id)
    assert (cancelled["match_id"], cancelled["user_id"]) == (match_ids[1], a.user_id)
    assert (expired["match_id"], expired["user_id"]) == (match_ids[2], None)
    assert (accepted["match_id"], accepted["user_id"]) == (accepted_id, b.user_id)


def test_match_and_move_events(
    capsys: pytest.CaptureFixture[str],
    new_username: UsernameFactory,
    created_matches: list[str],
) -> None:
    with TestClient(create_app()) as client:
        x = create_player(client, new_username())
        o = create_player(client, new_username())
        with client.websocket_connect("/ws") as ws_x, client.websocket_connect("/ws") as ws_o:
            authenticate(ws_x, x)
            authenticate(ws_o, o)
            match_id = start_match(ws_x, ws_o, o, created_matches)
            send(ws_x, "MOVE", {"match_id": match_id, "cell": 4, "seq": 0})
            receive(ws_x, "MATCH_STATE", seq=1)
            for payload in (
                {"match_id": match_id, "cell": 0, "seq": 1},
                {"match_id": match_id, "cell": 0, "seq": 0},
                {},
            ):
                send(ws_x, "MOVE", payload)
                receive(ws_x, "ERROR")

    output = capsys.readouterr().out
    started = _details(output, "match.started")
    applied = _details(output, "move.applied")
    rejected = _details(output, "move.rejected")
    assert started == [
        {
            "match_id": match_id,
            "x_user_id": x.user_id,
            "x_username": x.username,
            "o_user_id": o.user_id,
            "o_username": o.username,
        }
    ]
    assert applied == [
        {"user_id": x.user_id, "match_id": match_id, "symbol": "X", "cell": 4, "seq": 1}
    ]
    assert [(d["user_id"], d["match_id"], d["code"]) for d in rejected] == [
        (x.user_id, match_id, "NOT_YOUR_TURN"),
        (x.user_id, match_id, "STALE_STATE"),
        (x.user_id, None, "INVALID_MESSAGE"),
    ]
