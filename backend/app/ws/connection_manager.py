import logging

from fastapi import WebSocket

from app.ws.protocol import WSMessageEnvelope

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # user_id -> WebSocket
        self.active_connections: dict[str, WebSocket] = {}
        # user_id -> username
        self.user_names: dict[str, str] = {}
        # user_id -> status ("FREE" | "IN_MATCH")
        self.presence_status: dict[str, str] = {}

    async def connect(self, user_id: str, username: str, websocket: WebSocket) -> None:
        """Registra nova conexão e notifica a rede sobre a presença do usuário."""
        self.active_connections[user_id] = websocket
        self.user_names[user_id] = username
        self.presence_status[user_id] = "FREE"

        # Notifica os OUTROS usuários sobre a chegada deste usuário
        await self.broadcast_presence_update(username, "FREE", exclude_user_id=user_id)

    async def disconnect(self, user_id: str) -> None:
        """Remove a conexão e avisa que o usuário ficou OFFLINE."""
        username = self.user_names.pop(user_id, None)
        self.active_connections.pop(user_id, None)
        self.presence_status.pop(user_id, None)

        if username:
            await self.broadcast_presence_update(username, "OFFLINE")

    def update_status(self, user_id: str, status: str) -> None:
        """Atualiza o status (ex: FREE para IN_MATCH) e transmite a alteração."""
        if user_id in self.presence_status:
            self.presence_status[user_id] = status
            username = self.user_names.get(user_id)
            if username:
                import asyncio

                asyncio.create_task(self.broadcast_presence_update(username, status))

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
        import contextlib

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
