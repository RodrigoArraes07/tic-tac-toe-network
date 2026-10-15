import asyncio
import contextlib
import json
import logging

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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    authenticated_user_id: str | None = None
    authenticated_username: str | None = None

    auth_service: AuthService = websocket.app.state.auth_service
    event_bus: EventBus = websocket.app.state.event_bus
    engine: GameEngineService = websocket.app.state.game_engine

    # Autenticação Inicial
    try:
        raw_data = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)

        if len(raw_data.encode("utf-8")) > MAX_MESSAGE_SIZE_BYTES:
            await websocket.close(code=1009, reason="Mensagem grande demais")
            return

        envelope_dict = json.loads(raw_data)
        envelope = WSMessageEnvelope(**envelope_dict)

        if envelope.type != "AUTH":
            await websocket.close(code=4401, reason="Primeira mensagem deve ser AUTH")
            return

        auth_payload = AuthPayload(**envelope.payload)

        user = await auth_service.get_user_from_token(auth_payload.token)

        if not user:
            logger.warning("ws.auth_failed: token invalido ou usuario nao encontrado")
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

        await event_bus.publish(
            Event(
                type="user.connected",
                user_id=authenticated_user_id,
                data={"username": authenticated_username},
            )
        )

    except Exception as err:
        logger.error(f"ws.handshake_error: {type(err).__name__} - {err}")
        with contextlib.suppress(Exception):
            await websocket.close(code=4401, reason="Não autenticado")
        return

    # Loop Principal
    try:
        while True:
            raw_data = await websocket.receive_text()

            if len(raw_data.encode("utf-8")) > MAX_MESSAGE_SIZE_BYTES:
                await websocket.close(code=1009, reason="Mensagem excedeu 4KB")
                break

            try:
                envelope_dict = json.loads(raw_data)
                envelope = WSMessageEnvelope(**envelope_dict)

                await event_bus.publish(
                    Event(
                        type=f"cmd.{envelope.type.lower()}",
                        user_id=authenticated_user_id,
                        data={
                            "envelope": envelope.model_dump(),
                            "username": authenticated_username,
                        },
                    )
                )
            except json.JSONDecodeError, ValidationError:
                err_msg = WSMessageEnvelope(
                    type="ERROR",
                    payload={
                        "code": "INVALID_MESSAGE",
                        "message": "JSON malformado ou fora do schema",
                    },
                )
                await websocket.send_text(err_msg.model_dump_json())

    except WebSocketDisconnect:
        pass
    finally:
        went_offline = authenticated_user_id is not None and await connection_manager.disconnect(
            authenticated_user_id, websocket
        )
        if went_offline:
            await event_bus.publish(
                Event(
                    type="user.disconnected",
                    user_id=authenticated_user_id,
                    data={"username": authenticated_username},
                )
            )
