import logging
from typing import Any

from pydantic import ValidationError

from app.core.event_bus import Event, EventBus
from app.domain.enums import MatchResultType
from app.repositories.matches import MatchRepository
from app.services.game_engine import GameEngineService, GameError, MatchOutcome, MatchSnapshot
from app.services.ranking import RankingService
from app.ws.connection_manager import ConnectionManager
from app.ws.protocol import ForfeitPayload, MovePayload, WSMessageEnvelope

FREE_STATUS = "FREE"
ERROR_MESSAGES = {
    "INVALID_MESSAGE": "Mensagem fora do formato esperado.",
    "MATCH_NOT_FOUND": "Partida não encontrada.",
    "NOT_A_PLAYER": "Você não pertence a esta partida.",
    "INVALID_STATE": "Ação incompatível com o estado da partida.",
    "STALE_STATE": "Estado desatualizado.",
    "NOT_YOUR_TURN": "Aguarde sua vez.",
    "INVALID_CELL": "Casa inválida.",
    "CELL_OCCUPIED": "Casa já marcada.",
}
DEFAULT_ERROR_MESSAGE = "Comando recusado."

logger = logging.getLogger(__name__)


async def _send(connections: ConnectionManager, user_id: str, envelope: WSMessageEnvelope) -> None:
    try:
        await connections.send_personal_message(user_id, envelope.model_dump_json())
    except Exception:
        # Socket fechado no meio do envio: os outros destinatários ainda recebem.
        logger.warning("ws.send_failed", extra={"details": {"user_id": user_id}})


def _match_state(
    state: MatchSnapshot, last_move: dict[str, Any] | None, ref: str | None
) -> WSMessageEnvelope:
    return WSMessageEnvelope(
        type="MATCH_STATE",
        ref=ref,
        payload={
            "match_id": state.match_id,
            "board": state.board,
            "turn": state.turn.value,
            "seq": state.seq,
            "last_move": last_move,
        },
    )


def _result_for(outcome: MatchOutcome, user_id: str) -> MatchResultType:
    if outcome.winner_id is None:
        return MatchResultType.DRAW
    return MatchResultType.WIN if outcome.winner_id == user_id else MatchResultType.LOSS


class MatchFinisher:
    """Único ponto de encerramento de partida, qualquer que seja o motivo."""

    def __init__(
        self,
        connections: ConnectionManager,
        ranking_service: RankingService,
        match_repository: MatchRepository,
    ) -> None:
        self._connections = connections
        self._ranking_service = ranking_service
        self._match_repository = match_repository

    async def finish(self, outcome: MatchOutcome, ref: str | None = None) -> None:
        await self._notify_players(outcome, ref)
        await self._update_ranking(outcome)
        await self._save_history(outcome)
        for player in outcome.players:
            self._connections.update_status(player.user_id, FREE_STATUS)
        self._log_match_ended(outcome)

    async def _notify_players(self, outcome: MatchOutcome, ref: str | None) -> None:
        for player in outcome.players:
            envelope = WSMessageEnvelope(
                type="MATCH_ENDED",
                ref=ref,
                payload={
                    "match_id": outcome.match_id,
                    "result": _result_for(outcome, player.user_id).value,
                    "reason": outcome.reason.value,
                    "winning_line": outcome.winning_line,
                    "board": outcome.board,
                },
            )
            await _send(self._connections, player.user_id, envelope)

    async def _update_ranking(self, outcome: MatchOutcome) -> None:
        try:
            if outcome.winner_id is None or outcome.loser_id is None:
                await self._ranking_service.record_draw(
                    outcome.player_x.user_id, outcome.player_o.user_id
                )
            else:
                await self._ranking_service.record_win(outcome.winner_id, outcome.loser_id)
        except Exception:
            self._log_internal_error("ranking", outcome)

    async def _save_history(self, outcome: MatchOutcome) -> None:
        try:
            await self._match_repository.create_match_record(
                match_id=outcome.match_id,
                player_x_id=outcome.player_x.user_id,
                player_o_id=outcome.player_o.user_id,
                winner_id=outcome.winner_id,
                reason=outcome.reason.value,
            )
        except Exception:
            self._log_internal_error("match_history", outcome)

    def _log_internal_error(self, component: str, outcome: MatchOutcome) -> None:
        details = {"component": component, "match_id": outcome.match_id}
        logger.error("error.internal", extra={"details": details}, exc_info=True)

    def _log_match_ended(self, outcome: MatchOutcome) -> None:
        winner = next((p.username for p in outcome.players if p.user_id == outcome.winner_id), None)
        duration = (outcome.ended_at - outcome.started_at).total_seconds()
        details = {
            "match_id": outcome.match_id,
            "players": [player.username for player in outcome.players],
            "winner": winner,
            "reason": outcome.reason.value,
            "duration_s": round(duration, 1),
            "moves": outcome.moves,
        }
        logger.info("match.ended", extra={"details": details})


class GameHandlers:
    def __init__(
        self,
        engine: GameEngineService,
        finisher: MatchFinisher,
        connections: ConnectionManager,
    ) -> None:
        self._engine = engine
        self._finisher = finisher
        self._connections = connections

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe("cmd.move", self.handle_move)
        bus.subscribe("cmd.forfeit", self.handle_forfeit)
        bus.subscribe("user.disconnected", self.handle_user_disconnected)

    async def handle_move(self, event: Event) -> None:
        if not event.user_id:
            return
        envelope = event.data.get("envelope", {})
        ref = envelope.get("id")
        try:
            payload = MovePayload.model_validate(envelope.get("payload", {}))
        except ValidationError:
            await self._send_error(event.user_id, "INVALID_MESSAGE", ref)
            return
        try:
            result = await self._engine.make_move(
                event.user_id, payload.match_id, payload.cell, payload.seq
            )
        except GameError as err:
            await self._send_error(event.user_id, err.code, ref)
            if err.code == "STALE_STATE":
                await self._resend_state(event.user_id, payload.match_id, ref)
            return

        state_message = _match_state(result.state, result.last_move, ref)
        for user_id in result.state.player_ids:
            await _send(self._connections, user_id, state_message)
        if result.outcome is not None:
            await self._finisher.finish(result.outcome, ref)

    async def handle_forfeit(self, event: Event) -> None:
        if not event.user_id:
            return
        envelope = event.data.get("envelope", {})
        ref = envelope.get("id")
        try:
            payload = ForfeitPayload.model_validate(envelope.get("payload", {}))
            outcome = await self._engine.forfeit(event.user_id, payload.match_id)
        except ValidationError:
            await self._send_error(event.user_id, "INVALID_MESSAGE", ref)
            return
        except GameError as err:
            await self._send_error(event.user_id, err.code, ref)
            return
        await self._finisher.finish(outcome, ref)

    async def handle_user_disconnected(self, event: Event) -> None:
        if not event.user_id:
            return
        outcome = await self._engine.handle_player_disconnect(event.user_id)
        if outcome is not None:
            await self._finisher.finish(outcome)

    async def _resend_state(self, user_id: str, match_id: str, ref: str | None) -> None:
        state = self._engine.get_state(match_id)
        if state is not None:
            await _send(self._connections, user_id, _match_state(state, None, ref))

    async def _send_error(self, user_id: str, code: str, ref: str | None) -> None:
        envelope = WSMessageEnvelope(
            type="ERROR",
            ref=ref,
            payload={"code": code, "message": ERROR_MESSAGES.get(code, DEFAULT_ERROR_MESSAGE)},
        )
        await _send(self._connections, user_id, envelope)
