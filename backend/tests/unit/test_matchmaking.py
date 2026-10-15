import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.game_engine import GameEngineService, MatchOutcome
from app.services.matchmaking import MatchmakingService


async def _ignore_match_end(outcome: MatchOutcome) -> None:
    pass


def _service() -> MatchmakingService:
    return MatchmakingService(GameEngineService(on_match_end=_ignore_match_end))


@pytest.mark.asyncio
async def test_add_player_to_queue():
    service = _service()
    added = await service.add_player("user_1", "Player1")
    assert added is True
    assert len(service._queue) == 1


@pytest.mark.asyncio
async def test_prevent_duplicate_player_in_queue():
    service = _service()
    await service.add_player("user_1", "Player1")
    duplicate_added = await service.add_player("user_1", "Player1")

    assert duplicate_added is False
    assert len(service._queue) == 1


@pytest.mark.asyncio
async def test_remove_player_from_queue():
    service = _service()
    await service.add_player("user_1", "Player1")

    removed = await service.remove_player("user_1")
    assert removed is True
    assert len(service._queue) == 0


@pytest.mark.asyncio
async def test_matchmaking_triggers_match_when_two_players_join():
    service = _service()

    target = "app.ws.connection_manager.connection_manager.send_personal_message"
    with patch(target, new_callable=AsyncMock) as mock_send:
        # Adiciona o primeiro jogador
        await service.add_player("user_1", "Player1")
        assert len(service._queue) == 1
        mock_send.assert_not_called()

        # Adiciona o segundo jogador
        await service.add_player("user_2", "Player2")
        assert len(service._queue) == 0

        # Aguarda as tarefas assíncronas
        await asyncio.sleep(0.01)

        # Garante o envio das mensagens
        assert mock_send.call_count == 2
