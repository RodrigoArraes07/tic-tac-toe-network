import asyncio
import contextlib
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.event_bus import Event, EventBus
from app.services.auth import AuthService
from app.services.game_engine import GameEngineService
from app.ws.connection_manager import connection_manager
from app.ws.protocol import AuthPayload, WSMessageEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_MESSAGE_SIZE_BYTES = 4096
AUTH_TIMEOUT_SECONDS = 5.0
MESSAGE_TOO_BIG_CODE = 1009
AUTH_EVENT = "cmd.auth"
ERROR_MESSAGES = {
    "INVALID_MESSAGE": "JSON malformado ou fora do schema.",
    "INVALID_STATE": "Conexão já autenticada.",
    "UNKNOWN_TYPE": "Tipo de mensagem desconhecido.",
}


def _readable_id(message: Any) -> str | None:
    if isinstance(message, dict) and isinstance(message.get("id"), str):
        return message["id"]
    return None


async def _send_error(websocket: WebSocket, code: str, ref: str | None) -> None:
    envelope = WSMessageEnvelope(
        type="ERROR", ref=ref, payload={"code": code, "message": ERROR_MESSAGES[code]}
    )
    await websocket.send_text(envelope.model_dump_json())


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    authenticated_user_id: str | None = None
    authenticated_username: str | None = None

    auth_service: AuthService = websocket.app.state.auth_service
    event_bus: EventBus = websocket.app.state.event_bus
    engine: GameEngineService = websocket.app.state.game_engine
    client_ip = websocket.client.host if websocket.client else None
    client_port = websocket.client.port if websocket.client else None
    close_code: int | None = None

    # Autenticação Inicial
    try:
        raw_data = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)

        if len(raw_data.encode("utf-8")) > MAX_MESSAGE_SIZE_BYTES:
            await websocket.close(code=MESSAGE_TOO_BIG_CODE, reason="Mensagem grande demais")
            return

        envelope_dict = json.loads(raw_data)
        envelope = WSMessageEnvelope(**envelope_dict)

        if envelope.type != "AUTH":
            await websocket.close(code=4401, reason="Primeira mensagem deve ser AUTH")
            return

        auth_payload = AuthPayload(**envelope.payload)

        user = await auth_service.get_user_from_token(auth_payload.token)

        if not user:
            details = {"ip": client_ip, "reason": "invalid_token"}
            logger.warning("security.auth_failed", extra={"details": details})
            await websocket.close(code=4401, reason="Token inválido ou expirado")
            return

        user_id_val = getattr(user, "id", None) or getattr(user, "_id", None)
        authenticated_user_id = str(user_id_val)
        authenticated_username = str(user.username)

        await connection_manager.connect(authenticated_user_id, authenticated_username, websocket)

        auth_ok_msg = WSMessageEnvelope(
            type="AUTH_OK",
            ref=envelope.id,
            payload={
                "user": {"id": authenticated_user_id, "username": authenticated_username},
                "active_match_id": engine.active_match_of(authenticated_user_id),
            },
        )
        await websocket.send_text(auth_ok_msg.model_dump_json())

        snapshot_msg = WSMessageEnvelope(
            type="PRESENCE_SNAPSHOT",
            payload={"users": connection_manager.get_presence_snapshot()},
        )
        await websocket.send_text(snapshot_msg.model_dump_json())

        connected_at = time.monotonic()
        connection_details = {
            "user_id": authenticated_user_id,
            "username": authenticated_username,
            "ip": client_ip,
            "port": client_port,
        }
        logger.info("user.connected", extra={"details": connection_details})

        await event_bus.publish(
            Event(
                type="user.connected",
                user_id=authenticated_user_id,
                data={"username": authenticated_username},
            )
        )

    except Exception as err:
        details = {"ip": client_ip, "reason": type(err).__name__}
        logger.warning("security.auth_failed", extra={"details": details})
        with contextlib.suppress(Exception):
            await websocket.close(code=4401, reason="Não autenticado")
        return

    # Loop Principal
    try:
        while True:
            raw_data = await websocket.receive_text()

            if len(raw_data.encode("utf-8")) > MAX_MESSAGE_SIZE_BYTES:
                close_code = MESSAGE_TOO_BIG_CODE
                await websocket.close(code=close_code, reason="Mensagem excedeu 4KB")
                break

            parsed: Any = None
            try:
                parsed = json.loads(raw_data)
                envelope = WSMessageEnvelope.model_validate(parsed)
            except json.JSONDecodeError, ValidationError:
                await _send_error(websocket, "INVALID_MESSAGE", _readable_id(parsed))
                continue

            event_type = f"cmd.{envelope.type.lower()}"
            if event_type == AUTH_EVENT:
                await _send_error(websocket, "INVALID_STATE", _readable_id(parsed))
                continue
            if not event_bus.has_subscribers(event_type):
                await _send_error(websocket, "UNKNOWN_TYPE", _readable_id(parsed))
                continue

            await event_bus.publish(
                Event(
                    type=event_type,
                    user_id=authenticated_user_id,
                    data={
                        "envelope": envelope.model_dump(),
                        "username": authenticated_username,
                    },
                )
            )

    except WebSocketDisconnect as disconnect:
        close_code = disconnect.code
    finally:
        went_offline = authenticated_user_id is not None and await connection_manager.disconnect(
            authenticated_user_id, websocket
        )
        if went_offline:
            duration = round(time.monotonic() - connected_at, 1)
            details = {**connection_details, "close_code": close_code, "duration_s": duration}
            logger.info("user.disconnected", extra={"details": details})
            await event_bus.publish(
                Event(
                    type="user.disconnected",
                    user_id=authenticated_user_id,
                    data={"username": authenticated_username},
                )
            )
