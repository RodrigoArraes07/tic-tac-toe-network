from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.auth import get_auth_service
from app.api.matches import get_match_repository
from app.main import create_app
from app.repositories.users import User
from tests.integration.ws_helpers import (
    authenticate,
    create_player,
    receive,
    send,
    start_match,
)

HISTORY_KEYS = {"id", "player_x_id", "player_o_id", "winner_id", "reason", "ended_at"}


def test_get_matches_history_unauthenticated():
    """Garante rejeição (401) ao buscar histórico sem token."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/matches/history")
        assert response.status_code == 401


def test_get_matches_history_authenticated():
    """Garante retorno do histórico (200 OK) para usuário autenticado utilizando mocks."""
    app = create_app()

    # Instância válida de User contendo todos os campos exigidos
    mock_user = User(
        id="user_123",
        username="history_player",
        password_hash="hash",
        created_at=datetime.now(UTC),
        last_login_at=datetime.now(UTC),
        stats={"wins": 0, "losses": 0, "draws": 0},
    )

    # Mock do AuthService para retornar o usuário autenticado via token de teste
    mock_auth_service = MagicMock()
    mock_auth_service.get_user_from_token = AsyncMock(return_value=mock_user)

    # Mock do MatchRepository para retornar lista vazia
    mock_match_repo = MagicMock()
    mock_match_repo.get_user_matches = AsyncMock(return_value=[])

    # Sobrescreve as dependências REST no FastAPI
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    app.dependency_overrides[get_match_repository] = lambda: mock_match_repo

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer fake-test-token"}
        response = client.get("/api/matches/history", headers=headers)

        assert response.status_code == 200
        assert response.json() == []

    app.dependency_overrides.clear()


def test_history_lists_the_finished_match_with_id(
    new_username: Callable[[], str], created_matches: list[str]
) -> None:
    with TestClient(create_app()) as client:
        x = create_player(client, new_username())
        o = create_player(client, new_username())
        with client.websocket_connect("/ws") as ws_x, client.websocket_connect("/ws") as ws_o:
            authenticate(ws_x, x)
            authenticate(ws_o, o)
            match_id = start_match(ws_x, ws_o, o, created_matches)
            send(ws_o, "FORFEIT", {"match_id": match_id})
            receive(ws_x, "MATCH_ENDED", match_id=match_id)
            receive(ws_x, "PRESENCE_UPDATE", username=o.username, status="FREE")

        response = client.get(
            "/api/matches/history", headers={"Authorization": f"Bearer {x.token}"}
        )

    history = response.json()
    assert response.status_code == 200
    assert len(history) == 1
    assert history[0].keys() == HISTORY_KEYS
    assert history[0]["id"] == match_id
    assert (history[0]["player_x_id"], history[0]["player_o_id"]) == (x.user_id, o.user_id)
    assert (history[0]["winner_id"], history[0]["reason"]) == (x.user_id, "FORFEIT")
    assert datetime.fromisoformat(history[0]["ended_at"])
