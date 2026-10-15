from app.core.event_bus import Event, event_bus
from app.services.matchmaking import matchmaking_service


async def handle_join_queue(event: Event) -> None:
    if not event.user_id:
        return
    username = event.data.get("username", "Jogador")
    await matchmaking_service.add_player(event.user_id, username)


async def handle_leave_queue(event: Event) -> None:
    if not event.user_id:
        return
    await matchmaking_service.remove_player(event.user_id)


async def handle_user_disconnected(event: Event) -> None:
    if not event.user_id:
        return
    await matchmaking_service.remove_player(event.user_id)


def setup_matchmaking_handlers() -> None:
    """Registra os ouvintes no EventBus."""
    event_bus.subscribe("cmd.join_queue", handle_join_queue)
    event_bus.subscribe("cmd.leave_queue", handle_leave_queue)
    event_bus.subscribe("user.disconnected", handle_user_disconnected)
