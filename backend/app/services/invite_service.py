import asyncio
import logging
import uuid
from dataclasses import dataclass

from app.services.game_engine import GameEngineService
from app.ws.connection_manager import ConnectionManager
from app.ws.protocol import WSMessageEnvelope

IN_MATCH_STATUS = "IN_MATCH"
ERROR_MESSAGES = {
    "SELF_INVITE": "Você não pode convidar a si mesmo.",
    "USER_OFFLINE": "Usuário não está online.",
    "USER_BUSY": "Um dos jogadores já está em partida ou com convite pendente.",
    "INVALID_STATE": "Convite inexistente ou já encerrado.",
    "NOT_A_PLAYER": "Você não pode agir sobre este convite.",
}

logger = logging.getLogger(__name__)


@dataclass
class PendingInvite:
    match_id: str
    from_user_id: str
    from_username: str
    to_user_id: str
    to_username: str
    timer: asyncio.Task[None] | None = None

    def involves(self, user_id: str) -> bool:
        return user_id in (self.from_user_id, self.to_user_id)


class InviteService:
    def __init__(
        self, engine: GameEngineService, connections: ConnectionManager, timeout_s: int
    ) -> None:
        self._engine = engine
        self._connections = connections
        self._timeout_s = timeout_s
        # match_id -> PendingInvite
        self.pending_invites: dict[str, PendingInvite] = {}

    async def send_invite(
        self, from_user_id: str, from_username: str, to_username: str, msg_id: str | None
    ) -> None:
        to_username = to_username.lower()
        if from_username.lower() == to_username:
            await self.send_error(from_user_id, "SELF_INVITE", msg_id)
            return

        to_user_id = self._connections.get_user_id_by_username(to_username)
        if not to_user_id:
            await self.send_error(from_user_id, "USER_OFFLINE", msg_id)
            return

        if self._is_busy(from_user_id) or self._is_busy(to_user_id):
            await self.send_error(from_user_id, "USER_BUSY", msg_id)
            return

        match_id = str(uuid.uuid4())
        invite = PendingInvite(
            match_id=match_id,
            from_user_id=from_user_id,
            from_username=from_username,
            to_user_id=to_user_id,
            to_username=to_username,
        )
        invite.timer = asyncio.create_task(self._expire(match_id))
        self.pending_invites[match_id] = invite

        await self._send(
            from_user_id,
            WSMessageEnvelope(
                type="INVITE_SENT",
                ref=msg_id,
                payload={
                    "match_id": match_id,
                    "to_username": to_username,
                    "expires_in": self._timeout_s,
                },
            ),
        )
        await self._send(
            to_user_id,
            WSMessageEnvelope(
                type="INVITE_RECEIVED",
                payload={
                    "match_id": match_id,
                    "from_username": from_username,
                    "expires_in": self._timeout_s,
                },
            ),
        )

    async def respond_invite(
        self, user_id: str, match_id: str, accept: bool, msg_id: str | None
    ) -> None:
        invite = self.pending_invites.get(match_id)
        if invite is None:
            await self.send_error(user_id, "INVALID_STATE", msg_id)
            return
        if user_id != invite.to_user_id:
            await self.send_error(user_id, "NOT_A_PLAYER", msg_id)
            return
        self._take(match_id)

        if accept:
            await self._start_match(invite)
        else:
            await self._send_result(invite.from_user_id, match_id, "REJECTED")

    async def cancel_invite(self, user_id: str, match_id: str, msg_id: str | None) -> None:
        invite = self.pending_invites.get(match_id)
        if invite is None:
            await self.send_error(user_id, "INVALID_STATE", msg_id)
            return
        if user_id != invite.from_user_id:
            await self.send_error(user_id, "NOT_A_PLAYER", msg_id)
            return
        self._take(match_id)
        await self._send_result(invite.from_user_id, match_id, "CANCELLED", msg_id)
        await self._send_result(invite.to_user_id, match_id, "CANCELLED")

    async def cancel_invites_of(self, user_id: str) -> None:
        """Na desconexão, encerra os convites do usuário e avisa a outra parte."""
        for match_id in [m for m, i in self.pending_invites.items() if i.involves(user_id)]:
            invite = self._take(match_id)
            if invite is None:
                continue
            other_id = invite.to_user_id if user_id == invite.from_user_id else invite.from_user_id
            await self._send_result(other_id, match_id, "CANCELLED")

    def close(self) -> None:
        """Cancela os temporizadores pendentes ao desligar o servidor."""
        for invite in self.pending_invites.values():
            if invite.timer is not None:
                invite.timer.cancel()

    async def send_error(self, user_id: str, code: str, msg_id: str | None) -> None:
        await self._send(
            user_id,
            WSMessageEnvelope(
                type="ERROR",
                ref=msg_id,
                payload={"code": code, "message": ERROR_MESSAGES.get(code, "Comando recusado.")},
            ),
        )

    def _is_busy(self, user_id: str) -> bool:
        in_match = self._connections.presence_status.get(user_id) == IN_MATCH_STATUS
        return in_match or any(i.involves(user_id) for i in self.pending_invites.values())

    def _take(self, match_id: str) -> PendingInvite | None:
        """Única saída do estado pendente: remove o convite e cancela o timer."""
        invite = self.pending_invites.pop(match_id, None)
        # A tarefa de expiração também passa por aqui; cancelá-la interromperia
        # o aviso de EXPIRED que ela ainda vai enviar.
        if invite and invite.timer is not None and invite.timer is not asyncio.current_task():
            invite.timer.cancel()
        return invite

    async def _expire(self, match_id: str) -> None:
        await asyncio.sleep(self._timeout_s)
        invite = self._take(match_id)
        if invite is None:
            return
        logger.info("invite.expired", extra={"details": {"match_id": match_id}})
        await self._send_result(invite.from_user_id, match_id, "EXPIRED")
        await self._send_result(invite.to_user_id, match_id, "EXPIRED")

    async def _start_match(self, invite: PendingInvite) -> None:
        self._connections.update_status(invite.from_user_id, IN_MATCH_STATUS)
        self._connections.update_status(invite.to_user_id, IN_MATCH_STATUS)
        await self._engine.create_match(
            match_id=invite.match_id,
            p1_id=invite.from_user_id,
            p1_username=invite.from_username,
            p2_id=invite.to_user_id,
            p2_username=invite.to_username,
        )
        await self._send_match_started(invite, invite.from_user_id, "X", invite.to_username)
        await self._send_match_started(invite, invite.to_user_id, "O", invite.from_username)

    async def _send_match_started(
        self, invite: PendingInvite, user_id: str, symbol: str, opponent_username: str
    ) -> None:
        await self._send(
            user_id,
            WSMessageEnvelope(
                type="MATCH_STARTED",
                payload={
                    "match_id": invite.match_id,
                    "you_are": symbol,
                    "opponent": opponent_username,
                    "board": [None] * 9,
                    "turn": "X",
                    "seq": 0,
                },
            ),
        )

    async def _send_result(
        self, user_id: str, match_id: str, status: str, msg_id: str | None = None
    ) -> None:
        await self._send(
            user_id,
            WSMessageEnvelope(
                type="INVITE_RESULT",
                ref=msg_id,
                payload={"match_id": match_id, "status": status},
            ),
        )

    async def _send(self, user_id: str, envelope: WSMessageEnvelope) -> None:
        try:
            await self._connections.send_personal_message(user_id, envelope.model_dump_json())
        except Exception:
            # Socket fechado no meio do envio: os outros destinatários ainda recebem.
            logger.warning("ws.send_failed", extra={"details": {"user_id": user_id}})
