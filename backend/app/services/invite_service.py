import logging
import uuid
from dataclasses import dataclass

from app.services.game_engine import GameEngineService
from app.ws.connection_manager import connection_manager
from app.ws.protocol import WSMessageEnvelope

logger = logging.getLogger(__name__)


@dataclass
class PendingInvite:
    match_id: str
    from_user_id: str
    from_username: str
    to_user_id: str
    to_username: str


class InviteService:
    def __init__(self, engine: GameEngineService) -> None:
        self._engine = engine
        # match_id -> PendingInvite
        self.pending_invites: dict[str, PendingInvite] = {}

    async def send_invite(
        self, from_user_id: str, from_username: str, to_username: str, msg_id: str
    ) -> None:
        # Validação: Convidou a si mesmo?
        if from_username == to_username:
            err = WSMessageEnvelope(
                type="ERROR",
                ref=msg_id,
                payload={"code": "SELF_INVITE", "message": "Você não pode convidar a si mesmo."},
            )
            await connection_manager.send_personal_message(from_user_id, err.model_dump_json())
            return

        # Validação: Usuário de destino online?
        to_user_id = connection_manager.get_user_id_by_username(to_username)
        if not to_user_id:
            err = WSMessageEnvelope(
                type="ERROR",
                ref=msg_id,
                payload={"code": "USER_OFFLINE", "message": "Usuário não está online."},
            )
            await connection_manager.send_personal_message(from_user_id, err.model_dump_json())
            return

        # Validação: Algum dos dois já está em partida?
        if (
            connection_manager.presence_status.get(from_user_id) == "IN_MATCH"
            or connection_manager.presence_status.get(to_user_id) == "IN_MATCH"
        ):
            err = WSMessageEnvelope(
                type="ERROR",
                ref=msg_id,
                payload={"code": "USER_BUSY", "message": "Um dos jogadores já está em partida."},
            )
            await connection_manager.send_personal_message(from_user_id, err.model_dump_json())
            return

        match_id = str(uuid.uuid4())
        invite = PendingInvite(
            match_id=match_id,
            from_user_id=from_user_id,
            from_username=from_username,
            to_user_id=to_user_id,
            to_username=to_username,
        )
        self.pending_invites[match_id] = invite

        # Notifica o Convidante (INVITE_SENT)
        sent_msg = WSMessageEnvelope(
            type="INVITE_SENT",
            ref=msg_id,
            payload={"match_id": match_id, "to_username": to_username, "expires_in": 30},
        )
        await connection_manager.send_personal_message(from_user_id, sent_msg.model_dump_json())

        # Notifica o Convidado (INVITE_RECEIVED)
        rec_msg = WSMessageEnvelope(
            type="INVITE_RECEIVED",
            payload={"match_id": match_id, "from_username": from_username, "expires_in": 30},
        )
        await connection_manager.send_personal_message(to_user_id, rec_msg.model_dump_json())

    async def respond_invite(self, user_id: str, match_id: str, accept: bool, msg_id: str) -> None:
        invite = self.pending_invites.pop(match_id, None)
        if not invite:
            err = WSMessageEnvelope(
                type="ERROR",
                ref=msg_id,
                payload={"code": "INVALID_STATE", "message": "Convite inexistente ou expirado."},
            )
            await connection_manager.send_personal_message(user_id, err.model_dump_json())
            return

        if accept:
            # Atualiza presença para IN_MATCH
            connection_manager.update_status(invite.from_user_id, "IN_MATCH")
            connection_manager.update_status(invite.to_user_id, "IN_MATCH")

            # Cria partida na Engine
            await self._engine.create_match(
                match_id=match_id,
                p1_id=invite.from_user_id,
                p1_username=invite.from_username,
                p2_id=invite.to_user_id,
                p2_username=invite.to_username,
            )

            # Envia MATCH_STARTED para ambos
            start_msg_p1 = WSMessageEnvelope(
                type="MATCH_STARTED",
                payload={
                    "match_id": match_id,
                    "you_are": "X",
                    "opponent": {"id": invite.to_user_id, "username": invite.to_username},
                    "board": [None] * 9,
                    "turn": "X",
                    "seq": 0,
                },
            )
            start_msg_p2 = WSMessageEnvelope(
                type="MATCH_STARTED",
                payload={
                    "match_id": match_id,
                    "you_are": "O",
                    "opponent": {"id": invite.from_user_id, "username": invite.from_username},
                    "board": [None] * 9,
                    "turn": "X",
                    "seq": 0,
                },
            )
            await connection_manager.send_personal_message(
                invite.from_user_id, start_msg_p1.model_dump_json()
            )
            await connection_manager.send_personal_message(
                invite.to_user_id, start_msg_p2.model_dump_json()
            )
        else:
            # Convite rejeitado: notifica quem convidou
            res_msg = WSMessageEnvelope(
                type="INVITE_RESULT", payload={"match_id": match_id, "status": "REJECTED"}
            )
            await connection_manager.send_personal_message(
                invite.from_user_id, res_msg.model_dump_json()
            )
