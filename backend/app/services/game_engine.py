import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.enums import EndReason, Symbol
from app.domain.tictactoe import apply_move

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

            match.timeout_task = asyncio.create_task(
                self._schedule_turn_timeout(match_id, match.current_turn)
            )

            logger.info(
                "game_engine.match_started",
                extra={"details": {"match_id": match_id, "p1": p1_id, "p2": p2_id}},
            )
            return match

    async def make_move(self, user_id: str, cell: int) -> dict[str, Any]:
        """Aplica a jogada com trava de concorrência atômica por partida."""
        async with self._lock:  # Proteção contra race conditions / jogadas fora de ordem
            match_id = self._player_match_map.get(user_id)
            if not match_id:
                return {"error": "MATCH_NOT_FOUND", "message": "Partida não encontrada."}

            match = self._matches.get(match_id)
            if not match or match.is_finished:
                return {"error": "INVALID_STATE", "message": "Partida encerrada ou inválida."}

            player = match.players.get(user_id)
            if not player:
                return {"error": "NOT_A_PLAYER", "message": "Usuário não pertence à partida."}

            try:
                new_board, next_turn, result = apply_move(
                    board=match.board,
                    current_turn=match.current_turn,
                    cell=cell,
                    player_symbol=player.symbol,
                )
            except ValueError as err:
                reason = str(err).replace(" ", "_")
                logger.warning(
                    "game_engine.invalid_move",
                    extra={"details": {"user_id": user_id, "reason": reason}},
                )
                return {"error": reason, "message": "Jogada recusada pelas regras do jogo."}

            if match.timeout_task:
                match.timeout_task.cancel()

            match.board = new_board

            # Checa finalização (vitória ou empate)
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
                return {
                    "success": True,
                    "game_over": True,
                    "match": match,
                    "winner_id": winner_id,
                    "reason": end_reason,
                }

            # Partida continua
            match.current_turn = next_turn
            match.turn_expires_at = datetime.now(UTC) + timedelta(seconds=30)
            match.timeout_task = asyncio.create_task(
                self._schedule_turn_timeout(match_id, match.current_turn)
            )

            return {
                "success": True,
                "game_over": False,
                "match": match,
            }

    async def handle_player_disconnect(self, user_id: str) -> dict[str, Any] | None:
        """Encerra a partida com o motivo DISCONNECT caso um jogador caia."""
        async with self._lock:
            match_id = self._player_match_map.get(user_id)
            if not match_id:
                return None

            match = self._matches.get(match_id)
            if not match or match.is_finished:
                return None

            winner = next((p for p in match.players.values() if p.user_id != user_id), None)
            winner_id = winner.user_id if winner else None

            await self._finish_match(match, winner_id=winner_id, reason=EndReason.DISCONNECT)
            return {
                "match": match,
                "winner_id": winner_id,
                "reason": EndReason.DISCONNECT,
            }

    async def _schedule_turn_timeout(self, match_id: str, turn: Symbol) -> None:
        """Timeout de 30s para W.O. (FORFEIT)."""
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
                await self._finish_match(match, winner_id=winner.user_id, reason=EndReason.FORFEIT)
        except asyncio.CancelledError:
            pass

    async def _finish_match(
        self, match: ActiveMatch, winner_id: str | None, reason: EndReason
    ) -> None:
        """Limpa o estado da partida em memória."""
        match.is_finished = True
        if match.timeout_task:
            match.timeout_task.cancel()

        for uid in match.players:
            self._player_match_map.pop(uid, None)
        self._matches.pop(match.match_id, None)


game_engine_service = GameEngineService()
