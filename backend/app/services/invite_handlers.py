from functools import partial

from app.core.event_bus import Event, EventBus
from app.services.invite_service import InviteService


async def handle_invite_send(invite_service: InviteService, event: Event) -> None:
    if not event.user_id:
        return
    envelope = event.data.get("envelope", {})
    payload = envelope.get("payload", {})
    to_username = payload.get("to_username")
    username = event.data.get("username", "Jogador")
    msg_id = envelope.get("id")

    if to_username:
        await invite_service.send_invite(event.user_id, username, to_username, msg_id)


async def handle_invite_respond(invite_service: InviteService, event: Event) -> None:
    if not event.user_id:
        return
    envelope = event.data.get("envelope", {})
    payload = envelope.get("payload", {})
    match_id = payload.get("match_id")
    accept = payload.get("accept", False)
    msg_id = envelope.get("id")

    if match_id:
        await invite_service.respond_invite(event.user_id, match_id, accept, msg_id)


def setup_invite_handlers(bus: EventBus, invite_service: InviteService) -> None:
    """Inscreve os handlers no EventBus."""
    send = partial(handle_invite_send, invite_service)
    respond = partial(handle_invite_respond, invite_service)
    bus.subscribe("cmd.invite_send", send)
    bus.subscribe("cmd.INVITE_SEND", send)
    bus.subscribe("cmd.invite_respond", respond)
    bus.subscribe("cmd.INVITE_RESPOND", respond)
