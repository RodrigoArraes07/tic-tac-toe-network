import asyncio
from collections.abc import AsyncIterator

import pytest

from app.domain.enums import EndReason, Symbol
from app.services.game_engine import GameEngineService, GameError, MatchOutcome

SHORT_TURN_SECONDS = 0.05


class OutcomeRecorder:
    def __init__(self) -> None:
        self.outcomes: list[MatchOutcome] = []

    async def __call__(self, outcome: MatchOutcome) -> None:
        self.outcomes.append(outcome)


@pytest.fixture
def recorder() -> OutcomeRecorder:
    return OutcomeRecorder()


@pytest.fixture
async def service(recorder: OutcomeRecorder) -> AsyncIterator[GameEngineService]:
    engine = GameEngineService(on_match_end=recorder)
    yield engine
    engine.close()


async def test_create_match_initializes_players_and_board(service: GameEngineService) -> None:
    match = await service.create_match("m1", "p1", "Player1", "p2", "Player2")

    assert match.match_id == "m1"
    assert match.board == [None] * 9
    assert match.current_turn == Symbol.X
    assert match.seq == 0
    assert match.players["p1"].symbol == Symbol.X
    assert match.players["p2"].symbol == Symbol.CIRCLE


async def test_make_move_alternates_turn_and_increments_seq(service: GameEngineService) -> None:
    await service.create_match("m1", "p1", "Player1", "p2", "Player2")

    result = await service.make_move("p1", "m1", 0, 0)

    assert result.outcome is None
    assert result.state.board[0] == "X"
    assert result.state.turn == Symbol.CIRCLE
    assert result.state.seq == 1
    assert result.last_move == {"symbol": "X", "cell": 0}


async def test_make_move_out_of_turn_fails(service: GameEngineService) -> None:
    await service.create_match("m1", "p1", "Player1", "p2", "Player2")

    with pytest.raises(GameError) as error:
        await service.make_move("p2", "m1", 0, 0)

    assert error.value.code == "NOT_YOUR_TURN"


async def test_make_move_with_old_seq_is_stale(service: GameEngineService) -> None:
    await service.create_match("m1", "p1", "Player1", "p2", "Player2")
    await service.make_move("p1", "m1", 0, 0)

    with pytest.raises(GameError) as error:
        await service.make_move("p1", "m1", 1, 0)

    assert error.value.code == "STALE_STATE"
    state = service.get_state("m1")
    assert state is not None
    assert state.board == ["X", None, None, None, None, None, None, None, None]


async def test_winning_game_returns_the_outcome(service: GameEngineService) -> None:
    await service.create_match("m1", "p1", "Player1", "p2", "Player2")

    for seq, (player, cell) in enumerate([("p1", 0), ("p2", 3), ("p1", 1), ("p2", 4)]):
        await service.make_move(player, "m1", cell, seq)
    result = await service.make_move("p1", "m1", 2, 4)

    assert result.outcome is not None
    assert result.outcome.winner_id == "p1"
    assert result.outcome.reason == EndReason.LINE
    assert result.outcome.winning_line == [0, 1, 2]
    assert result.outcome.moves == 5
    assert service.get_state("m1") is None


async def test_forfeit_gives_the_win_to_the_opponent(service: GameEngineService) -> None:
    await service.create_match("m1", "p1", "Player1", "p2", "Player2")

    outcome = await service.forfeit("p2", "m1")

    assert outcome.winner_id == "p1"
    assert outcome.loser_id == "p2"
    assert outcome.reason == EndReason.FORFEIT


async def test_forfeit_outside_a_match_is_rejected(service: GameEngineService) -> None:
    await service.create_match("m1", "p1", "Player1", "p2", "Player2")

    codes = []
    for user_id, match_id in [("p1", "inexistente"), ("p3", "m1")]:
        with pytest.raises(GameError) as error:
            await service.forfeit(user_id, match_id)
        codes.append(error.value.code)
    await service.forfeit("p1", "m1")
    with pytest.raises(GameError) as finished:
        await service.forfeit("p1", "m1")

    assert codes == ["MATCH_NOT_FOUND", "NOT_A_PLAYER"]
    assert finished.value.code == "INVALID_STATE"


async def test_turn_timeout_ends_the_match_through_the_callback(
    recorder: OutcomeRecorder,
) -> None:
    engine = GameEngineService(on_match_end=recorder, turn_timeout_seconds=SHORT_TURN_SECONDS)
    await engine.create_match("m1", "p1", "Player1", "p2", "Player2")

    await asyncio.sleep(SHORT_TURN_SECONDS * 4)

    assert len(recorder.outcomes) == 1
    assert recorder.outcomes[0].winner_id == "p2"
    assert recorder.outcomes[0].reason == EndReason.TIMEOUT


SHORT_GRACE_SECONDS = 0.15


async def test_disconnect_suspends_the_turn_and_expires_with_disconnect(
    recorder: OutcomeRecorder,
) -> None:
    engine = GameEngineService(
        on_match_end=recorder,
        turn_timeout_seconds=SHORT_TURN_SECONDS,
        reconnect_grace_seconds=SHORT_GRACE_SECONDS,
    )
    await engine.create_match("m1", "p1", "Player1", "p2", "Player2")

    change = await engine.handle_player_disconnect("p1")
    await asyncio.sleep(SHORT_TURN_SECONDS * 2)
    during_window = list(recorder.outcomes)
    await asyncio.sleep(SHORT_GRACE_SECONDS * 2)

    assert change is not None
    assert (change.match_id, change.opponent_id) == ("m1", "p2")
    assert during_window == []
    assert len(recorder.outcomes) == 1
    assert recorder.outcomes[0].reason == EndReason.DISCONNECT
    assert recorder.outcomes[0].winner_id == "p2"


async def test_reconnect_closes_the_window_and_restarts_the_turn(
    recorder: OutcomeRecorder,
) -> None:
    engine = GameEngineService(
        on_match_end=recorder,
        turn_timeout_seconds=SHORT_TURN_SECONDS,
        reconnect_grace_seconds=SHORT_GRACE_SECONDS,
    )
    await engine.create_match("m1", "p1", "Player1", "p2", "Player2")
    await engine.handle_player_disconnect("p1")

    change = await engine.handle_player_reconnect("p1")
    not_away = await engine.handle_player_reconnect("p2")
    await asyncio.sleep(SHORT_TURN_SECONDS * 3)

    assert change is not None
    assert change.opponent_id == "p2"
    assert not_away is None
    assert [outcome.reason for outcome in recorder.outcomes] == [EndReason.TIMEOUT]
