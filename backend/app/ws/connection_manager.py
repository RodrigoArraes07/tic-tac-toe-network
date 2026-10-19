import asyncio
import contextlib
import logging

from fastapi import WebSocket

from app.ws.protocol import WSMessageEnvelope

SESSION_REPLACED_CODE = 4001
SESSION_REPLACED_REASON = "Sessão aberta em outra conexão"

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # user_id -> WebSocket
        self.active_connections: dict[str, WebSocket] = {}
        # user_id -> username
        self.user_names: dict[str, str] = {}
        # user_id -> status ("FREE" | "IN_MATCH")
        self.presence_status: dict[str, str] = {}
        self._broadcast_tasks: set[asyncio.Task[None]] = set()

    async def connect(self, user_id: str, username: str, websocket: WebSocket) -> None:
        """Registra a conexão; uma conexão anterior do mesmo usuário é fechada com 4001."""
        previous = self.active_connections.get(user_id)
        # A nova é registrada antes de fechar a antiga, para o disconnect da antiga
        # reconhecer que ela já não é a conexão do usuário.
        self.active_connections[user_id] = websocket
        self.user_names[user_id] = username
        if previous is not None:
            with contextlib.suppress(Exception):
                await previous.close(code=SESSION_REPLACED_CODE, reason=SESSION_REPLACED_REASON)
            return

        self.presence_status[user_id] = "FREE"
        await self.broadcast_presence_update(username, "FREE", exclude_user_id=user_id)

    async def disconnect(self, user_id: str, websocket: WebSocket) -> bool:
        """Remove a conexão e avisa OFFLINE, só se ela ainda for a registrada do usuário."""
        if self.active_connections.get(user_id) is not websocket:
            return False
        username = self.user_names.pop(user_id, None)
        self.active_connections.pop(user_id, None)
        self.presence_status.pop(user_id, None)

        if username:
            await self.broadcast_presence_update(username, "OFFLINE")
        return True

    def update_status(self, user_id: str, status: str) -> None:
        """Atualiza o status (ex: FREE para IN_MATCH) e transmite a alteração."""
        if user_id in self.presence_status:
            self.presence_status[user_id] = status
            username = self.user_names.get(user_id)
            if username:
                task = asyncio.create_task(self.broadcast_presence_update(username, status))
                self._broadcast_tasks.add(task)
                task.add_done_callback(self._broadcast_tasks.discard)

    def get_presence_snapshot(self) -> list[dict[str, str]]:
        """Retorna lista de todos os usuários online e seus status."""
        return [
            {"username": uname, "status": self.presence_status.get(uid, "FREE")}
            for uid, uname in self.user_names.items()
        ]

    async def broadcast_presence_update(
        self, username: str, status: str, exclude_user_id: str | None = None
    ) -> None:
        """Envia evento PRESENCE_UPDATE para as conexões ativas."""
        update_msg = WSMessageEnvelope(
            type="PRESENCE_UPDATE",
            payload={"username": username, "status": status},
        ).model_dump_json()

        for uid, ws in list(self.active_connections.items()):
            if uid != exclude_user_id:
                with contextlib.suppress(Exception):
                    await ws.send_text(update_msg)

    async def send_personal_message(self, user_id: str, message: str) -> None:
        """Envia mensagem direta para o WebSocket do usuário."""
        ws = self.active_connections.get(user_id)
        if ws:
            await ws.send_text(message)

    def get_user_id_by_username(self, username: str) -> str | None:
        """Helper para buscar o user_id através do username."""
        for uid, uname in self.user_names.items():
            if uname == username:
                return uid
        return None


connection_manager = ConnectionManager()
