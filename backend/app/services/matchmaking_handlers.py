from functools import partial

from app.core.event_bus import Event, EventBus
from app.services.matchmaking import MatchmakingService


async def handle_join_queue(matchmaking_service: MatchmakingService, event: Event) -> None:
    if not event.user_id:
        return
    username = event.data.get("username", "Jogador")
    await matchmaking_service.add_player(event.user_id, username)


async def handle_leave_queue(matchmaking_service: MatchmakingService, event: Event) -> None:
    if not event.user_id:
        return
    await matchmaking_service.remove_player(event.user_id)


async def handle_user_disconnected(matchmaking_service: MatchmakingService, event: Event) -> None:
    if not event.user_id:
        return
    await matchmaking_service.remove_player(event.user_id)


def setup_matchmaking_handlers(bus: EventBus, matchmaking_service: MatchmakingService) -> None:
    """Registra os ouvintes no EventBus."""
    bus.subscribe("cmd.join_queue", partial(handle_join_queue, matchmaking_service))
    bus.subscribe("cmd.leave_queue", partial(handle_leave_queue, matchmaking_service))
    bus.subscribe("user.disconnected", partial(handle_user_disconnected, matchmaking_service))
