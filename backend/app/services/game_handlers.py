from app.core.event_bus import Event, event_bus
from app.services.game_engine import game_engine_service


async def handle_make_move(event: Event) -> None:
    if not event.user_id:
        return
    
    envelope = event.data.get("envelope", {})
    payload = envelope.get("payload", {})
    cell = payload.get("cell")
    
    if cell is not None:
        await game_engine_service.make_move(event.user_id, cell)

def setup_game_handlers() -> None:
    """Registra os ouvintes de jogo no EventBus."""
    event_bus.subscribe("cmd.make_move", handle_make_move)
    event_bus.subscribe("cmd.MAKE_MOVE", handle_make_move)