from app.core.event_bus import Event, event_bus
from app.services.invite_service import invite_service


async def handle_invite_send(event: Event) -> None:
    if not event.user_id:
        return
    envelope = event.data.get("envelope", {})
    payload = envelope.get("payload", {})
    to_username = payload.get("to_username")
    username = event.data.get("username", "Jogador")
    msg_id = envelope.get("id")

    if to_username:
        await invite_service.send_invite(event.user_id, username, to_username, msg_id)


async def handle_invite_respond(event: Event) -> None:
    if not event.user_id:
        return
    envelope = event.data.get("envelope", {})
    payload = envelope.get("payload", {})
    match_id = payload.get("match_id")
    accept = payload.get("accept", False)
    msg_id = envelope.get("id")

    if match_id:
        await invite_service.respond_invite(event.user_id, match_id, accept, msg_id)


def setup_invite_handlers() -> None:
    """Inscreve os handlers no EventBus."""
    event_bus.subscribe("cmd.invite_send", handle_invite_send)
    event_bus.subscribe("cmd.INVITE_SEND", handle_invite_send)
    event_bus.subscribe("cmd.invite_respond", handle_invite_respond)
    event_bus.subscribe("cmd.INVITE_RESPOND", handle_invite_respond)
