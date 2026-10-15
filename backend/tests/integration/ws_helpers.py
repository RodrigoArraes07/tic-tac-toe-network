from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

PASSWORD = "senha-correta-123"

type Message = dict[str, Any]


@dataclass(frozen=True)
class Player:
    username: str
    user_id: str
    token: str


def create_player(client: TestClient, username: str) -> Player:
    credentials = {"username": username, "password": PASSWORD}
    user_id = client.post("/api/auth/register", json=credentials).json()["id"]
    token = client.post("/api/auth/login", json=credentials).json()["access_token"]
    return Player(username=username, user_id=user_id, token=token)


def send(ws: WebSocketTestSession, message_type: str, payload: dict[str, Any]) -> str:
    message_id = str(uuid4())
    ws.send_json({"type": message_type, "id": message_id, "ref": None, "payload": payload})
    return message_id


def receive(ws: WebSocketTestSession, message_type: str, **expected: Any) -> Message:
    while True:
        message = ws.receive_json()
        payload = message["payload"]
        if message["type"] == message_type and all(
            payload.get(k) == v for k, v in expected.items()
        ):
            return message


def receive_presence_free(ws: WebSocketTestSession, *usernames: str) -> None:
    pending = set(usernames)
    while pending:
        pending.discard(receive(ws, "PRESENCE_UPDATE", status="FREE")["payload"]["username"])


def authenticate(ws: WebSocketTestSession, player: Player) -> None:
    send(ws, "AUTH", {"token": player.token})
    receive(ws, "AUTH_OK")


def start_match(
    ws_x: WebSocketTestSession,
    ws_o: WebSocketTestSession,
    player_o: Player,
    created_matches: list[str],
) -> str:
    send(ws_x, "INVITE_SEND", {"to_username": player_o.username})
    match_id = receive(ws_o, "INVITE_RECEIVED")["payload"]["match_id"]
    created_matches.append(match_id)
    send(ws_o, "INVITE_RESPOND", {"match_id": match_id, "accept": True})
    for ws in (ws_x, ws_o):
        started = receive(ws, "MATCH_STARTED", match_id=match_id)
        assert started["payload"]["seq"] == 0
    return match_id


def play(
    ws_x: WebSocketTestSession, ws_o: WebSocketTestSession, match_id: str, cells: list[int]
) -> None:
    for seq, cell in enumerate(cells):
        mover = ws_x if seq % 2 == 0 else ws_o
        send(mover, "MOVE", {"match_id": match_id, "cell": cell, "seq": seq})
        for ws in (ws_x, ws_o):
            state = receive(ws, "MATCH_STATE", seq=seq + 1)
            assert state["payload"]["last_move"]["cell"] == cell
