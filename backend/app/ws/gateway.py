import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.event_bus import Event, event_bus
from app.services.auth import AuthService
from app.ws.connection_manager import connection_manager
from app.ws.protocol import AuthPayload, WSMessageEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_MESSAGE_SIZE_BYTES = 4096  # Regra de tamanho máximo: 4 KB


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    authenticated_user_id: str | None = None
    authenticated_username: str | None = None

    auth_service: AuthService = websocket.app.state.auth_service

    # --- PASSO 1: Autenticação Inicial (AUTH obrigatório em até 5 segundos) ---
    try:
        raw_data = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)

        if len(raw_data.encode("utf-8")) > MAX_MESSAGE_SIZE_BYTES:
            await websocket.close(code=1009, reason="Mensagem grande demais")
            return

        envelope_dict = json.loads(raw_data)
        envelope = WSMessageEnvelope(**envelope_dict)

        if envelope.type != "AUTH":
            await websocket.close(code=4401, reason="Primeira mensagem deve ser AUTH")
            return

        auth_payload = AuthPayload(**envelope.payload)

        # Autentica o usuário via JWT
        user = await auth_service.get_user_from_token(auth_payload.token)

        if not user:
            logger.warning("ws.auth_failed: token invalido ou usuario nao encontrado")
            await websocket.close(code=4401, reason="Token inválido ou expirado")
            return

        user_id_val = getattr(user, "id", None) or getattr(user, "_id", None)
        authenticated_user_id = str(user_id_val)
        authenticated_username = str(user.username)

        # Registra a conexão ativa (sem chamar accept novamente)
        await connection_manager.connect(authenticated_user_id, websocket)

        # Responde AUTH_OK
        auth_ok_msg = WSMessageEnvelope(
            type="AUTH_OK",
            ref=envelope.id,
            payload={
                "user": {"id": authenticated_user_id, "username": authenticated_username},
                "active_match_id": None,
            },
        )
        await websocket.send_text(auth_ok_msg.model_dump_json())

        # Publica evento de conexão no barramento
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

    # --- PASSO 2: Loop Principal de Mensagens ---
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
                        data={"envelope": envelope.model_dump(),
                              "username": authenticated_username},
                    )
                )
            except (json.JSONDecodeError, ValidationError):
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
        if authenticated_user_id:
            connection_manager.disconnect(authenticated_user_id)
            await event_bus.publish(
                Event(
                    type="user.disconnected",
                    user_id=authenticated_user_id,
                    data={"username": authenticated_username},
                )
            )