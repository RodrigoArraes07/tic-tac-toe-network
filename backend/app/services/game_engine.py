import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.domain.enums import EndReason, MatchResultType, Symbol
from app.domain.tictactoe import apply_move
from app.ws.connection_manager import connection_manager
from app.ws.protocol import (
    GameOverPayload,
    GameStatePayload,
    WSMessageEnvelope,
)

logger = logging.getLogger(__name__)


@dataclass
class PlayerSession:
    user_id: str
    username: str
    symbol: Symbol


@dataclass
class ActiveMatch:
    match_id: str
    players: dict[str, PlayerSession]  
    board: list[str | None] = field(default_factory=lambda: [None] * 9)
    current_turn: Symbol = Symbol.X
    turn_expires_at: datetime = field(
        default_factory=lambda: datetime.now(UTC) + timedelta(seconds=30)
    )
    timeout_task: asyncio.Task | None = None
    is_finished: bool = False


class GameEngineService:
    def __init__(self) -> None:
        self._matches: dict[str, ActiveMatch] = {}
        self._player_match_map: dict[str, str] = {} 
        self._lock = asyncio.Lock()

    async def create_match(
        self,
        match_id: str,
        p1_id: str,
        p1_username: str,
        p2_id: str,
        p2_username: str,
    ) -> ActiveMatch:
        """Inicializa uma partida ativa entre dois jogadores."""
        async with self._lock:
            p1 = PlayerSession(user_id=p1_id, username=p1_username, symbol=Symbol.X)
            p2 = PlayerSession(user_id=p2_id, username=p2_username, symbol=Symbol.CIRCLE)

            match = ActiveMatch(
                match_id=match_id,
                players={p1_id: p1, p2_id: p2},
            )

            self._matches[match_id] = match
            self._player_match_map[p1_id] = match_id
            self._player_match_map[p2_id] = match_id

            # Agenda o timeout da primeira jogada 
            match.timeout_task = asyncio.create_task(
                self._schedule_turn_timeout(match_id, match.current_turn)
            )

            logger.info(
                "game_engine.match_started",
                extra={"details": {"match_id": match_id, "p1": p1_id, "p2": p2_id}},
            )
            return match

    async def make_move(self, user_id: str, cell: int) -> bool:
        """Aplica a jogada utilizando as regras e validações do apply_move."""
        match_id = self._player_match_map.get(user_id)
        if not match_id:
            return False

        match = self._matches.get(match_id)
        if not match or match.is_finished:
            return False

        player = match.players.get(user_id)
        if not player:
            return False

        # Tenta aplicar a jogada usando a sua função pura
        try:
            new_board, next_turn, result = apply_move(
                board=match.board,
                current_turn=match.current_turn,
                cell=cell,
                player_symbol=player.symbol,
            )
        except ValueError as err:
            logger.warning(
                "game_engine.invalid_move",
                extra={"details": {"user_id": user_id, "reason": str(err)}},
            )
            return False

        # Cancela o timer de timeout do turno anterior
        if match.timeout_task:
            match.timeout_task.cancel()

        # Atualiza o estado da partida
        match.board = new_board

        # Verifica se a partida terminou (Vitória por linha ou Empate)
        if result and result.get("finished"):
            winner_symbol_val = result.get("winner")
            winner_id = None
            if winner_symbol_val:
                winner_player = next(
                    p for p in match.players.values() if p.symbol.value == winner_symbol_val
                )
                winner_id = winner_player.user_id

            end_reason = EndReason(result["reason"])
            await self._finish_match(match, winner_id=winner_id, reason=end_reason)
            return True

        # Partida continua: avança para o próximo turno
        match.current_turn = next_turn
        match.turn_expires_at = datetime.now(UTC) + timedelta(seconds=30)

        # Agenda o timeout para o próximo jogador
        match.timeout_task = asyncio.create_task(
            self._schedule_turn_timeout(match_id, match.current_turn)
        )

        # Transmite o novo estado do tabuleiro via WebSocket
        await self._broadcast_game_state(match)
        return True

    async def _schedule_turn_timeout(self, match_id: str, turn: Symbol) -> None:
        """Aguarda 30s e declara derrota por W.O. caso o jogador estoure o tempo."""
        try:
            await asyncio.sleep(30)
            match = self._matches.get(match_id)
            if match and not match.is_finished and match.current_turn == turn:
                loser = next(p for p in match.players.values() if p.symbol == turn)
                winner = next(p for p in match.players.values() if p.symbol != turn)
                logger.info(
                    "game_engine.turn_timeout",
                    extra={"details": {"match_id": match_id, "loser": loser.user_id}},
                )
                await self._finish_match(
                    match, winner_id=winner.user_id, reason=EndReason.FORFEIT
                )
        except asyncio.CancelledError:
            pass

    async def _broadcast_game_state(self, match: ActiveMatch) -> None:
        """Notifica os dois jogadores do novo estado do tabuleiro."""
        payload = GameStatePayload(
            match_id=match.match_id,
            board=match.board,
            current_turn=match.current_turn,
            turn_expires_at=match.turn_expires_at.isoformat(),
        ).model_dump()

        envelope = WSMessageEnvelope(type="GAME_STATE", payload=payload)
        msg_json = envelope.model_dump_json()

        await asyncio.gather(
            *(
                connection_manager.send_personal_message(uid, msg_json)
                for uid in match.players
            ),
            return_exceptions=True,
        )

    async def _finish_match(
        self, match: ActiveMatch, winner_id: str | None, reason: EndReason
    ) -> None:
        """Finaliza a partida e notifica ambos com os resultados (WIN/LOSS/DRAW)."""
        match.is_finished = True
        if match.timeout_task:
            match.timeout_task.cancel()

        for uid, _player in match.players.items():
            if reason == EndReason.DRAW:
                result_type = MatchResultType.DRAW
            elif uid == winner_id:
                result_type = MatchResultType.WIN
            else:
                result_type = MatchResultType.LOSS

            payload = GameOverPayload(
                match_id=match.match_id,
                winner_id=winner_id,
                reason=reason,
                result_type=result_type,
            ).model_dump()

            envelope = WSMessageEnvelope(type="GAME_OVER", payload=payload)
            await connection_manager.send_personal_message(
                uid, envelope.model_dump_json()
            )

        # Limpa da memória
        async with self._lock:
            for uid in match.players:
                self._player_match_map.pop(uid, None)
            self._matches.pop(match.match_id, None)


game_engine_service = GameEngineService()