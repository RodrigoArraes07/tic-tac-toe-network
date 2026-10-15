from pydantic import BaseModel, ValidationError

from app.core.event_bus import Event, EventBus
from app.services.invite_service import InviteService
from app.ws.protocol import InviteCancelPayload, InviteRespondPayload, InviteSendPayload


class InviteHandlers:
    def __init__(self, invite_service: InviteService) -> None:
        self._invites = invite_service

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe("cmd.invite_send", self.handle_invite_send)
        bus.subscribe("cmd.invite_respond", self.handle_invite_respond)
        bus.subscribe("cmd.invite_cancel", self.handle_invite_cancel)
        bus.subscribe("user.disconnected", self.handle_user_disconnected)

    async def handle_invite_send(self, event: Event) -> None:
        payload = await self._validate(event, InviteSendPayload)
        if event.user_id and isinstance(payload, InviteSendPayload):
            username = event.data.get("username", "")
            await self._invites.send_invite(
                event.user_id, username, payload.to_username, self._ref(event)
            )

    async def handle_invite_respond(self, event: Event) -> None:
        payload = await self._validate(event, InviteRespondPayload)
        if event.user_id and isinstance(payload, InviteRespondPayload):
            await self._invites.respond_invite(
                event.user_id, payload.match_id, payload.accept, self._ref(event)
            )

    async def handle_invite_cancel(self, event: Event) -> None:
        payload = await self._validate(event, InviteCancelPayload)
        if event.user_id and isinstance(payload, InviteCancelPayload):
            await self._invites.cancel_invite(event.user_id, payload.match_id, self._ref(event))

    async def handle_user_disconnected(self, event: Event) -> None:
        if event.user_id:
            await self._invites.cancel_invites_of(event.user_id)

    @staticmethod
    def _ref(event: Event) -> str | None:
        return event.data.get("envelope", {}).get("id")

    async def _validate(self, event: Event, model: type[BaseModel]) -> BaseModel | None:
        if not event.user_id:
            return None
        try:
            return model.model_validate(event.data.get("envelope", {}).get("payload", {}))
        except ValidationError:
            await self._invites.send_error(event.user_id, "INVALID_MESSAGE", self._ref(event))
            return None
