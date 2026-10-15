import contextlib

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # Mapeia user_id -> WebSocket
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        if user_id in self.active_connections:
            old_ws = self.active_connections[user_id]
            with contextlib.suppress(Exception):
                await old_ws.close(code=4001, reason="Sessão aberta em outro local")

        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str) -> None:
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, user_id: str, message: str) -> None:
        if user_id in self.active_connections:
            ws = self.active_connections[user_id]
            await ws.send_text(message)


connection_manager = ConnectionManager()
