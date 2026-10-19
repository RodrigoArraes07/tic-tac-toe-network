import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.domain.enums import EndReason, Symbol
from app.domain.tictactoe import apply_move

TURN_TIMEOUT_SECONDS = 30.0
RECONNECT_GRACE_SECONDS = 30.0
BOARD_SIZE = 9

logger = logging.getLogger(__name__)


class GameError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PlayerSession:
    user_id: str
    username: str
    symbol: Symbol


@dataclass
class ActiveMatch:
    match_id: str
    players: dict[str, PlayerSession]
    turn_expires_at: datetime
    board: list[str | None] = field(default_factory=lambda: [None] * BOARD_SIZE)
    current_turn: Symbol = Symbol.X
    seq: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    timeout_task: asyncio.Task[None] | None = None
    # Jogadores fora do ar, cada um com o timer da sua janela de reconexão.
    grace_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    is_finished: bool = False

    def player_with(self, symbol: Symbol) -> PlayerSession:
        return next(player for player in self.players.values() if player.symbol == symbol)

    def opponent_of(self, user_id: str) -> PlayerSession:
        return next(player for player in self.players.values() if player.user_id != user_id)


@dataclass(frozen=True)
class MatchSnapshot:
    match_id: str
    player_ids: tuple[str, ...]
    board: list[str | None]
    turn: Symbol
    seq: int


@dataclass(frozen=True)
class PlayerView:
    state: MatchSnapshot
    you_are: Symbol
    opponent: str


@dataclass(frozen=True)
class MatchOutcome:
    match_id: str
    player_x: PlayerSession
    player_o: PlayerSession
    winner_id: str | None
    reason: EndReason
    winning_line: list[int] | None
    board: list[str | None]
    moves: int
    started_at: datetime
    ended_at: datetime

    @property
    def players(self) -> tuple[PlayerSession, PlayerSession]:
        return self.player_x, self.player_o

    @property
    def loser_id(self) -> str | None:
        if self.winner_id is None:
            return None
        return next(p.user_id for p in self.players if p.user_id != self.winner_id)


@dataclass(frozen=True)
class ConnectionChange:
    match_id: str
    opponent_id: str


@dataclass(frozen=True)
class MoveResult:
    state: MatchSnapshot
    last_move: dict[str, int | str]
    outcome: MatchOutcome | None


type MatchEndCallback = Callable[[MatchOutcome], Awaitable[None]]


def _snapshot(match: ActiveMatch) -> MatchSnapshot:
    return MatchSnapshot(
        match_id=match.match_id,
        player_ids=tuple(match.players),
        board=list(match.board),
        turn=match.current_turn,
        seq=match.seq,
    )


class GameEngineService:
    def __init__(
        self,
        on_match_end: MatchEndCallback,
        turn_timeout_seconds: float = TURN_TIMEOUT_SECONDS,
        reconnect_grace_seconds: float = RECONNECT_GRACE_SECONDS,
    ) -> None:
        self._on_match_end = on_match_end
        self._turn_timeout_seconds = turn_timeout_seconds
        self._reconnect_grace_seconds = reconnect_grace_seconds
        self._matches: dict[str, ActiveMatch] = {}
        self._player_match_map: dict[str, str] = {}
        self._finished_match_ids: set[str] = set()
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
                turn_expires_at=self._next_turn_deadline(),
            )
            self._matches[match_id] = match
            self._player_match_map[p1_id] = match_id
            self._player_match_map[p2_id] = match_id
            self._start_turn_timer(match)
            logger.info(
                "game_engine.match_started",
                extra={"details": {"match_id": match_id, "p1": p1_id, "p2": p2_id}},
            )
            return match

    def active_match_of(self, user_id: str) -> str | None:
        return self._player_match_map.get(user_id)

    async def sync(self, user_id: str, match_id: str) -> PlayerView:
        """Estado atual do ponto de vista de quem pediu (símbolo e adversário)."""
        async with self._lock:
            match = self._require_player_match(user_id, match_id)
            return PlayerView(
                state=_snapshot(match),
                you_are=match.players[user_id].symbol,
                opponent=match.opponent_of(user_id).username,
            )

    def get_state(self, match_id: str) -> MatchSnapshot | None:
        match = self._matches.get(match_id)
        return _snapshot(match) if match else None

    async def make_move(self, user_id: str, match_id: str, cell: int, seq: int) -> MoveResult:
        """Aplica a jogada com trava de concorrência; a partida encerrada vem no resultado."""
        async with self._lock:
            match = self._require_player_match(user_id, match_id)
            if seq != match.seq:
                raise GameError("STALE_STATE")
            player = match.players[user_id]
            try:
                new_board, next_turn, result = apply_move(
                    board=match.board,
                    current_turn=match.current_turn,
                    cell=cell,
                    player_symbol=player.symbol,
                )
            except ValueError as err:
                logger.warning(
                    "move.rejected",
                    extra={"details": {"match_id": match_id, "code": str(err)}},
                )
                raise GameError(str(err)) from err

            self._cancel_turn_timer(match)
            match.board = new_board
            match.seq += 1
            last_move: dict[str, int | str] = {"symbol": player.symbol.value, "cell": cell}

            if result is None:
                match.current_turn = next_turn
                match.turn_expires_at = self._next_turn_deadline()
                # Com alguém fora do ar o turno fica suspenso; volta na reconexão.
                if not match.grace_tasks:
                    self._start_turn_timer(match)
                return MoveResult(state=_snapshot(match), last_move=last_move, outcome=None)

            winner_symbol = result["winner"]
            winner_id = match.player_with(Symbol(winner_symbol)).user_id if winner_symbol else None
            outcome = self._finish(
                match,
                winner_id=winner_id,
                reason=EndReason(result["reason"]),
                winning_line=result["winning_line"],
            )
            return MoveResult(state=_snapshot(match), last_move=last_move, outcome=outcome)

    async def forfeit(self, user_id: str, match_id: str) -> MatchOutcome:
        """Desistência: o adversário vence com reason FORFEIT."""
        async with self._lock:
            match = self._require_player_match(user_id, match_id)
            winner = match.opponent_of(user_id)
            return self._finish(match, winner_id=winner.user_id, reason=EndReason.FORFEIT)

    async def handle_player_disconnect(self, user_id: str) -> ConnectionChange | None:
        """Abre a janela de reconexão: o turno fica suspenso até o jogador voltar."""
        async with self._lock:
            match = self._active_match_of(user_id)
            if match is None or user_id in match.grace_tasks:
                return None
            self._cancel_turn_timer(match)
            match.grace_tasks[user_id] = asyncio.create_task(
                self._expire_grace(match.match_id, user_id)
            )
            details = {
                "match_id": match.match_id,
                "user_id": user_id,
                "grace_s": self._reconnect_grace_seconds,
            }
            logger.info("match.player_disconnected", extra={"details": details})
            return ConnectionChange(match.match_id, match.opponent_of(user_id).user_id)

    async def handle_player_reconnect(self, user_id: str) -> ConnectionChange | None:
        """Fecha a janela e, sem ninguém mais fora, reinicia o turno de quem é a vez."""
        async with self._lock:
            match = self._active_match_of(user_id)
            if match is None or user_id not in match.grace_tasks:
                return None
            self._cancel_task(match.grace_tasks.pop(user_id))
            if not match.grace_tasks:
                match.turn_expires_at = self._next_turn_deadline()
                self._start_turn_timer(match)
            details = {"match_id": match.match_id, "user_id": user_id}
            logger.info("match.player_reconnected", extra={"details": details})
            return ConnectionChange(match.match_id, match.opponent_of(user_id).user_id)

    def close(self) -> None:
        """Cancela os temporizadores pendentes ao desligar o servidor."""
        for match in self._matches.values():
            self._cancel_turn_timer(match)
            self._cancel_grace_timers(match)

    def _active_match_of(self, user_id: str) -> ActiveMatch | None:
        match_id = self._player_match_map.get(user_id)
        match = self._matches.get(match_id) if match_id else None
        return None if match is None or match.is_finished else match

    def _require_player_match(self, user_id: str, match_id: str) -> ActiveMatch:
        match = self._matches.get(match_id)
        if match is None:
            code = "INVALID_STATE" if match_id in self._finished_match_ids else "MATCH_NOT_FOUND"
            raise GameError(code)
        if user_id not in match.players:
            raise GameError("NOT_A_PLAYER")
        if match.is_finished:
            raise GameError("INVALID_STATE")
        return match

    def _next_turn_deadline(self) -> datetime:
        return datetime.now(UTC) + timedelta(seconds=self._turn_timeout_seconds)

    def _start_turn_timer(self, match: ActiveMatch) -> None:
        match.timeout_task = asyncio.create_task(
            self._expire_turn(match.match_id, match.current_turn, match.seq)
        )

    def _cancel_turn_timer(self, match: ActiveMatch) -> None:
        if match.timeout_task is not None:
            self._cancel_task(match.timeout_task)
        match.timeout_task = None

    def _cancel_grace_timers(self, match: ActiveMatch) -> None:
        for task in match.grace_tasks.values():
            self._cancel_task(task)
        match.grace_tasks.clear()

    @staticmethod
    def _cancel_task(task: asyncio.Task[None]) -> None:
        # As tarefas de timeout chegam aqui ao encerrar a partida; cancelar a própria
        # interromperia o callback de fim de partida que ela ainda vai chamar.
        if task is not asyncio.current_task():
            task.cancel()

    async def _expire_turn(self, match_id: str, turn: Symbol, seq: int) -> None:
        await asyncio.sleep(self._turn_timeout_seconds)
        async with self._lock:
            match = self._matches.get(match_id)
            if match is None or match.is_finished or match.seq != seq:
                return
            loser = match.player_with(turn)
            logger.info(
                "game_engine.turn_timeout",
                extra={"details": {"match_id": match_id, "loser": loser.user_id}},
            )
            winner = match.opponent_of(loser.user_id)
            outcome = self._finish(match, winner_id=winner.user_id, reason=EndReason.TIMEOUT)
        await self._on_match_end(outcome)

    async def _expire_grace(self, match_id: str, user_id: str) -> None:
        await asyncio.sleep(self._reconnect_grace_seconds)
        async with self._lock:
            match = self._matches.get(match_id)
            if match is None or match.is_finished or user_id not in match.grace_tasks:
                return
            details = {"match_id": match_id, "user_id": user_id}
            logger.info("match.reconnect_expired", extra={"details": details})
            winner = match.opponent_of(user_id)
            outcome = self._finish(match, winner_id=winner.user_id, reason=EndReason.DISCONNECT)
        await self._on_match_end(outcome)

    def _finish(
        self,
        match: ActiveMatch,
        winner_id: str | None,
        reason: EndReason,
        winning_line: list[int] | None = None,
    ) -> MatchOutcome:
        match.is_finished = True
        self._cancel_turn_timer(match)
        self._cancel_grace_timers(match)
        for user_id in match.players:
            self._player_match_map.pop(user_id, None)
        self._matches.pop(match.match_id, None)
        self._finished_match_ids.add(match.match_id)
        return MatchOutcome(
            match_id=match.match_id,
            player_x=match.player_with(Symbol.X),
            player_o=match.player_with(Symbol.CIRCLE),
            winner_id=winner_id,
            reason=reason,
            winning_line=winning_line,
            board=list(match.board),
            moves=match.seq,
            started_at=match.started_at,
            ended_at=datetime.now(UTC),
        )
