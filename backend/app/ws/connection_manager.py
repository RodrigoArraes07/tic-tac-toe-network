from typing import Dict
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # Mapeia user_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        """Registra uma nova conexão, fechando a anterior se já existir."""
        if user_id in self.active_connections:
            old_ws = self.active_connections[user_id]
            try:
                await old_ws.close(code=4001, reason="Sessão aberta em outro local")
            except Exception:
                pass

        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str) -> None:
        """Remove a conexão ativa do registro."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: str, user_id: str) -> bool:
        """Envia mensagem de texto/JSON para um usuário específico."""
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.send_text(message)
                return True
            except Exception:
                self.disconnect(user_id)
        return False

    async def broadcast(self, message: str) -> None:
        """Envia mensagem para todos os usuários conectados."""
        for user_id, ws in list(self.active_connections.items()):
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(user_id)


connection_manager = ConnectionManager()