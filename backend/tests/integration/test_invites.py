import time
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.core.config import Settings
from app.main import create_app
from tests.integration.ws_helpers import (
    Message,
    Player,
    authenticate,
    closed_code,
    create_player,
    receive,
    send,
    start_match,
)

SHORT_INVITE_TIMEOUT_S = 1
WAIT_PAST_TIMEOUT_S = SHORT_INVITE_TIMEOUT_S + 0.5
SESSION_REPLACED_CODE = 4001
PRESENCE_TYPES = {"PRESENCE_UPDATE", "PRESENCE_SNAPSHOT"}

type UsernameFactory = Callable[[], str]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def short_invite_client() -> Iterator[TestClient]:
    settings = Settings(invite_timeout_s=SHORT_INVITE_TIMEOUT_S)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _players(client: TestClient, new_username: UsernameFactory, count: int) -> list[Player]:
    return [create_player(client, new_username()) for _ in range(count)]


def _next_non_presence(ws: WebSocketTestSession) -> Message:
    while True:
        message = ws.receive_json()
        if message["type"] not in PRESENCE_TYPES:
            return message


def _invite(ws_from: WebSocketTestSession, ws_to: WebSocketTestSession, to: Player) -> str:
    send(ws_from, "INVITE_SEND", {"to_username": to.username})
    return receive(ws_to, "INVITE_RECEIVED")["payload"]["match_id"]


def _error_code(ws: WebSocketTestSession) -> str:
    return receive(ws, "ERROR")["payload"]["code"]


def test_respond_from_a_third_user_is_refused_and_keeps_the_invite(
    client: TestClient, new_username: UsernameFactory
) -> None:
    a, b, c = _players(client, new_username, 3)
    with (
        client.websocket_connect("/ws") as ws_a,
        client.websocket_connect("/ws") as ws_b,
        client.websocket_connect("/ws") as ws_c,
    ):
        for ws, player in ((ws_a, a), (ws_b, b), (ws_c, c)):
            authenticate(ws, player)
        match_id = _invite(ws_a, ws_b, b)

        send(ws_c, "INVITE_RESPOND", {"match_id": match_id, "accept": True})
        third_party = _error_code(ws_c)
        send(ws_b, "INVITE_RESPOND", {"match_id": match_id, "accept": False})
        result = receive(ws_a, "INVITE_RESULT", match_id=match_id)["payload"]

    assert third_party == "NOT_A_PLAYER"
    assert result["status"] == "REJECTED"


def test_invite_expires_for_both_players(
    short_invite_client: TestClient, new_username: UsernameFactory
) -> None:
    a, b = _players(short_invite_client, new_username, 2)
    with (
        short_invite_client.websocket_connect("/ws") as ws_a,
        short_invite_client.websocket_connect("/ws") as ws_b,
    ):
        authenticate(ws_a, a)
        authenticate(ws_b, b)
        send(ws_a, "INVITE_SEND", {"to_username": b.username})
        sent = receive(ws_a, "INVITE_SENT")["payload"]
        received = receive(ws_b, "INVITE_RECEIVED")["payload"]
        match_id = sent["match_id"]

        expired_a = receive(ws_a, "INVITE_RESULT", match_id=match_id)["payload"]
        expired_b = receive(ws_b, "INVITE_RESULT", match_id=match_id)["payload"]
        send(ws_b, "INVITE_RESPOND", {"match_id": match_id, "accept": True})
        late_answer = _error_code(ws_b)

    assert sent["expires_in"] == received["expires_in"] == SHORT_INVITE_TIMEOUT_S
    assert expired_a["status"] == expired_b["status"] == "EXPIRED"
    assert late_answer == "INVALID_STATE"


def test_only_the_inviter_can_cancel(client: TestClient, new_username: UsernameFactory) -> None:
    a, b = _players(client, new_username, 2)
    with client.websocket_connect("/ws") as ws_a, client.websocket_connect("/ws") as ws_b:
        authenticate(ws_a, a)
        authenticate(ws_b, b)
        match_id = _invite(ws_a, ws_b, b)

        send(ws_b, "INVITE_CANCEL", {"match_id": match_id})
        invitee_cancel = _error_code(ws_b)
        cancel_id = send(ws_a, "INVITE_CANCEL", {"match_id": match_id})
        cancelled_a = receive(ws_a, "INVITE_RESULT", match_id=match_id)
        cancelled_b = receive(ws_b, "INVITE_RESULT", match_id=match_id)
        send(ws_b, "INVITE_RESPOND", {"match_id": match_id, "accept": True})
        late_answer = _error_code(ws_b)

    assert invitee_cancel == "NOT_A_PLAYER"
    assert cancelled_a["payload"]["status"] == cancelled_b["payload"]["status"] == "CANCELLED"
    assert cancelled_a["ref"] == cancel_id
    assert late_answer == "INVALID_STATE"


@pytest.mark.parametrize("leaver", ["inviter", "invitee"])
def test_disconnect_cancels_the_pending_invite(
    client: TestClient, new_username: UsernameFactory, leaver: str
) -> None:
    a, b = _players(client, new_username, 2)
    with client.websocket_connect("/ws") as ws_stays:
        stays, leaves = (b, a) if leaver == "inviter" else (a, b)
        authenticate(ws_stays, stays)
        with client.websocket_connect("/ws") as ws_leaves:
            authenticate(ws_leaves, leaves)
            if leaver == "inviter":
                match_id = _invite(ws_leaves, ws_stays, stays)
            else:
                match_id = _invite(ws_stays, ws_leaves, leaves)

        result = receive(ws_stays, "INVITE_RESULT", match_id=match_id)["payload"]

    assert result["status"] == "CANCELLED"


def test_pending_invite_makes_both_players_busy(
    client: TestClient, new_username: UsernameFactory
) -> None:
    a, b, c = _players(client, new_username, 3)
    with (
        client.websocket_connect("/ws") as ws_a,
        client.websocket_connect("/ws") as ws_b,
        client.websocket_connect("/ws") as ws_c,
    ):
        for ws, player in ((ws_a, a), (ws_b, b), (ws_c, c)):
            authenticate(ws, player)
        _invite(ws_a, ws_b, b)

        codes = []
        for ws_from, target in ((ws_c, a), (ws_c, b), (ws_a, c)):
            send(ws_from, "INVITE_SEND", {"to_username": target.username})
            codes.append(_error_code(ws_from))

    assert codes == ["USER_BUSY", "USER_BUSY", "USER_BUSY"]


def test_rejecting_or_cancelling_stops_the_expiration_timer(
    short_invite_client: TestClient, new_username: UsernameFactory
) -> None:
    a, b = _players(short_invite_client, new_username, 2)
    with (
        short_invite_client.websocket_connect("/ws") as ws_a,
        short_invite_client.websocket_connect("/ws") as ws_b,
    ):
        authenticate(ws_a, a)
        authenticate(ws_b, b)
        rejected_id = _invite(ws_a, ws_b, b)
        send(ws_b, "INVITE_RESPOND", {"match_id": rejected_id, "accept": False})
        receive(ws_a, "INVITE_RESULT", match_id=rejected_id, status="REJECTED")
        cancelled_id = _invite(ws_a, ws_b, b)
        send(ws_a, "INVITE_CANCEL", {"match_id": cancelled_id})
        receive(ws_a, "INVITE_RESULT", match_id=cancelled_id, status="CANCELLED")
        receive(ws_b, "INVITE_RESULT", match_id=cancelled_id, status="CANCELLED")

        time.sleep(WAIT_PAST_TIMEOUT_S)
        probes = []
        for match_id in (rejected_id, cancelled_id):
            send(ws_a, "INVITE_CANCEL", {"match_id": match_id})
            probes.append(_next_non_presence(ws_a))
            send(ws_b, "INVITE_RESPOND", {"match_id": match_id, "accept": True})
            probes.append(_next_non_presence(ws_b))

    assert [(m["type"], m["payload"]["code"]) for m in probes] == [("ERROR", "INVALID_STATE")] * 4


def test_accepting_stops_the_expiration_timer(
    short_invite_client: TestClient, new_username: UsernameFactory, created_matches: list[str]
) -> None:
    a, b = _players(short_invite_client, new_username, 2)
    with (
        short_invite_client.websocket_connect("/ws") as ws_a,
        short_invite_client.websocket_connect("/ws") as ws_b,
    ):
        authenticate(ws_a, a)
        authenticate(ws_b, b)
        match_id = start_match(ws_a, ws_b, b, created_matches)

        time.sleep(WAIT_PAST_TIMEOUT_S)
        send(ws_a, "INVITE_CANCEL", {"match_id": match_id})
        probe_a = _next_non_presence(ws_a)
        send(ws_b, "INVITE_RESPOND", {"match_id": match_id, "accept": True})
        probe_b = _next_non_presence(ws_b)

    assert [(m["type"], m["payload"]["code"]) for m in (probe_a, probe_b)] == [
        ("ERROR", "INVALID_STATE")
    ] * 2


def test_invite_payloads_are_validated(client: TestClient, new_username: UsernameFactory) -> None:
    (a,) = _players(client, new_username, 1)
    with client.websocket_connect("/ws") as ws_a:
        authenticate(ws_a, a)
        codes = []
        for message_type, payload in (
            ("INVITE_SEND", {"to_username": 123}),
            ("INVITE_RESPOND", {"match_id": "m1", "accept": "sim"}),
            ("INVITE_CANCEL", {}),
        ):
            message_id = send(ws_a, message_type, payload)
            error = receive(ws_a, "ERROR")
            codes.append((error["payload"]["code"], error["ref"] == message_id))

    assert codes == [("INVALID_MESSAGE", True)] * 3


def test_new_connection_replaces_the_old_one_and_keeps_presence(
    client: TestClient, new_username: UsernameFactory
) -> None:
    a, b, c = _players(client, new_username, 3)
    with client.websocket_connect("/ws") as ws_b:
        authenticate(ws_b, b)
        with client.websocket_connect("/ws") as ws_a1:
            authenticate(ws_a1, a)
            with client.websocket_connect("/ws") as ws_a2:
                authenticate(ws_a2, a)
                old_connection = closed_code(ws_a1)
                with client.websocket_connect("/ws") as ws_c:
                    send(ws_c, "AUTH", {"token": c.token})
                    snapshot = receive(ws_c, "PRESENCE_SNAPSHOT")["payload"]["users"]
                send(ws_b, "INVITE_SEND", {"to_username": a.username})
                invite = receive(ws_a2, "INVITE_RECEIVED")["payload"]

    assert old_connection == SESSION_REPLACED_CODE
    assert {"username": a.username, "status": "FREE"} in snapshot
    assert invite["from_username"] == b.username


def test_new_connection_resumes_the_match_in_progress(
    client: TestClient, new_username: UsernameFactory, created_matches: list[str]
) -> None:
    a, b = _players(client, new_username, 2)
    with client.websocket_connect("/ws") as ws_b, client.websocket_connect("/ws") as ws_a1:
        authenticate(ws_b, b)
        authenticate(ws_a1, a)
        match_id = start_match(ws_a1, ws_b, b, created_matches)
        with client.websocket_connect("/ws") as ws_a2:
            send(ws_a2, "AUTH", {"token": a.token})
            auth_ok = receive(ws_a2, "AUTH_OK")["payload"]
            old_connection = closed_code(ws_a1)
            sync_id = send(ws_a2, "MATCH_SYNC", {"match_id": match_id})
            synced = receive(ws_a2, "MATCH_STATE")
            send(ws_a2, "MOVE", {"match_id": match_id, "cell": 4, "seq": 0})
            state_a = receive(ws_a2, "MATCH_STATE", seq=1)["payload"]
            state_b = receive(ws_b, "MATCH_STATE", seq=1)["payload"]

    assert auth_ok["active_match_id"] == match_id
    assert old_connection == SESSION_REPLACED_CODE
    assert synced["ref"] == sync_id
    assert synced["payload"]["seq"] == 0
    assert synced["payload"]["turn"] == "X"
    assert synced["payload"]["board"] == [None] * 9
    assert state_a["board"][4] == state_b["board"][4] == "X"


def test_match_sync_outside_the_match_is_refused(
    client: TestClient, new_username: UsernameFactory, created_matches: list[str]
) -> None:
    a, b, c = _players(client, new_username, 3)
    with (
        client.websocket_connect("/ws") as ws_a,
        client.websocket_connect("/ws") as ws_b,
        client.websocket_connect("/ws") as ws_c,
    ):
        for ws, player in ((ws_a, a), (ws_b, b), (ws_c, c)):
            authenticate(ws, player)
        match_id = start_match(ws_a, ws_b, b, created_matches)

        codes = []
        for payload in ({"match_id": match_id}, {"match_id": "inexistente"}, {}):
            send(ws_c, "MATCH_SYNC", payload)
            codes.append(_error_code(ws_c))

    assert codes == ["NOT_A_PLAYER", "MATCH_NOT_FOUND", "INVALID_MESSAGE"]
