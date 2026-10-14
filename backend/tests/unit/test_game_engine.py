from unittest.mock import AsyncMock, patch

import pytest

from app.domain.enums import Symbol
from app.services.game_engine import GameEngineService


@pytest.mark.asyncio
async def test_create_match_initializes_players_and_board():
    service = GameEngineService()
    match = await service.create_match("m1", "p1", "Player1", "p2", "Player2")

    assert match.match_id == "m1"
    assert match.board == [None] * 9
    assert match.current_turn == Symbol.X
    assert match.players["p1"].symbol == Symbol.X
    assert match.players["p2"].symbol == Symbol.CIRCLE
    
    # Cancela a task de timeout para não pendurar o teste
    if match.timeout_task:
        match.timeout_task.cancel()


@pytest.mark.asyncio
async def test_make_move_alternates_turn_and_updates_board():
    service = GameEngineService()
    await service.create_match("m1", "p1", "Player1", "p2", "Player2")

    target = "app.ws.connection_manager.connection_manager.send_personal_message"
    with patch(target, new_callable=AsyncMock):
        # p1 (Symbol.X) joga na posição 0
        success = await service.make_move("p1", 0)
        assert success is True

        match = service._matches["m1"]
        assert match.board[0] == "X"
        assert match.current_turn == Symbol.CIRCLE

        # Cancela a task de timeout
        if match.timeout_task:
            match.timeout_task.cancel()


@pytest.mark.asyncio
async def test_make_move_out_of_turn_fails():
    service = GameEngineService()
    await service.create_match("m1", "p1", "Player1", "p2", "Player2")

    # p2 tenta jogar primeiro (sendo que é a vez do p1)
    success = await service.make_move("p2", 0)
    assert success is False

    match = service._matches["m1"]
    if match.timeout_task:
        match.timeout_task.cancel()


@pytest.mark.asyncio
async def test_winning_game_triggers_game_over():
    service = GameEngineService()
    await service.create_match("m1", "p1", "Player1", "p2", "Player2")

    target = "app.ws.connection_manager.connection_manager.send_personal_message"
    with patch(target, new_callable=AsyncMock) as mock_send:
        # Simulando uma vitória de p1 no topo (0, 1, 2)
        await service.make_move("p1", 0)  # X
        await service.make_move("p2", 3)  # O
        await service.make_move("p1", 1)  # X
        await service.make_move("p2", 4)  # O
        await service.make_move("p1", 2)  # X Vence!

        # Verifica se o evento de GAME_OVER foi transmitido
        assert mock_send.call_count > 0
        # A partida deve ter sido removida das partidas ativas após o término
        assert "m1" not in service._matches