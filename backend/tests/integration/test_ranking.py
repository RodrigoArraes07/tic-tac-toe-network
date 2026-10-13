from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pymongo.collection import Collection

from app.main import create_app
from app.repositories.users import UserNotFoundError

PASSWORD = "senha-correta-123"
MAX_RANKING_LIMIT = 100
RANKING_KEYS = {"position", "username", "points", "wins", "draws", "losses"}
UNKNOWN_USER_ID = "000000000000000000000000"
MALFORMED_USER_ID = "nao-e-um-id"
ZERO_STATS = {"wins": 0, "losses": 0, "draws": 0, "points": 0}

type UsernameFactory = Callable[[], str]
type UsersCollection = Collection[dict[str, Any]]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def _register(client: TestClient, username: str) -> str:
    credentials = {"username": username, "password": PASSWORD}
    return client.post("/api/auth/register", json=credentials).json()["id"]


def _auth_headers(client: TestClient, username: str) -> dict[str, str]:
    credentials = {"username": username, "password": PASSWORD}
    token = client.post("/api/auth/login", json=credentials).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _record(client: TestClient, result: str, first_id: str, second_id: str) -> None:
    assert client.portal is not None
    service: Any = client.app.state.ranking_service
    client.portal.call(getattr(service, result), first_id, second_id)


def _score(username: str, wins: int, draws: int, losses: int, points: int) -> dict[str, Any]:
    return {
        "username": username,
        "points": points,
        "wins": wins,
        "draws": draws,
        "losses": losses,
    }


def test_t21_ranking_shows_points_and_order_with_tiebreaks(
    client: TestClient, new_username: UsernameFactory
) -> None:
    top, loser, clean, beaten, drawer = (new_username() for _ in range(5))
    first_twin, second_twin = sorted(new_username() for _ in range(2))
    usernames = [top, loser, clean, beaten, drawer, first_twin, second_twin]
    ids = {username: _register(client, username) for username in usernames}

    _record(client, "record_win", ids[top], ids[loser])
    _record(client, "record_win", ids[top], ids[loser])
    _record(client, "record_win", ids[clean], ids[loser])
    _record(client, "record_win", ids[beaten], ids[loser])
    _record(client, "record_win", ids[loser], ids[beaten])
    _record(client, "record_draw", ids[drawer], ids[first_twin])
    _record(client, "record_draw", ids[second_twin], ids[drawer])
    _record(client, "record_draw", ids[drawer], ids[loser])

    response = client.get(
        "/api/ranking",
        params={"limit": MAX_RANKING_LIMIT},
        headers=_auth_headers(client, top),
    )

    entries = response.json()
    created = [entry for entry in entries if entry["username"] in ids]
    assert response.status_code == 200
    assert [entry["position"] for entry in entries] == list(range(1, len(entries) + 1))
    assert all(entry.keys() == RANKING_KEYS for entry in entries)
    assert [{key: entry[key] for key in entry if key != "position"} for entry in created] == [
        _score(top, wins=2, draws=0, losses=0, points=6),
        _score(loser, wins=1, draws=1, losses=4, points=4),
        _score(clean, wins=1, draws=0, losses=0, points=3),
        _score(beaten, wins=1, draws=0, losses=1, points=3),
        _score(drawer, wins=0, draws=3, losses=0, points=3),
        _score(first_twin, wins=0, draws=1, losses=0, points=1),
        _score(second_twin, wins=0, draws=1, losses=0, points=1),
    ]


def test_ranking_respects_the_limit(client: TestClient, new_username: UsernameFactory) -> None:
    usernames = [new_username() for _ in range(2)]
    for username in usernames:
        _register(client, username)

    response = client.get(
        "/api/ranking", params={"limit": 1}, headers=_auth_headers(client, usernames[0])
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_ranking_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/ranking")

    assert response.status_code == 401


@pytest.mark.parametrize("limit", ["0", "101", "-1", "abc"])
def test_ranking_with_invalid_limit_returns_422(
    client: TestClient, new_username: UsernameFactory, limit: str
) -> None:
    username = new_username()
    _register(client, username)

    response = client.get(
        "/api/ranking", params={"limit": limit}, headers=_auth_headers(client, username)
    )

    assert response.status_code == 422


def _stored_stats(users_collection: UsersCollection, username: str) -> Any:
    document = users_collection.find_one({"username": username})
    assert document is not None
    return document["stats"]


@pytest.mark.parametrize("result", ["record_win", "record_draw"])
@pytest.mark.parametrize("missing_id", [UNKNOWN_USER_ID, MALFORMED_USER_ID])
def test_result_with_a_missing_user_is_rejected_and_writes_nothing(
    client: TestClient,
    new_username: UsernameFactory,
    users_collection: UsersCollection,
    result: str,
    missing_id: str,
) -> None:
    username = new_username()
    user_id = _register(client, username)

    with pytest.raises(UserNotFoundError):
        _record(client, result, user_id, missing_id)
    with pytest.raises(UserNotFoundError):
        _record(client, result, missing_id, user_id)

    assert _stored_stats(users_collection, username) == ZERO_STATS


@pytest.mark.parametrize("result", ["record_win", "record_draw"])
def test_result_with_the_same_player_twice_is_rejected_and_writes_nothing(
    client: TestClient,
    new_username: UsernameFactory,
    users_collection: UsersCollection,
    result: str,
) -> None:
    username = new_username()
    user_id = _register(client, username)

    with pytest.raises(ValueError, match="dois jogadores diferentes"):
        _record(client, result, user_id, user_id)

    assert _stored_stats(users_collection, username) == ZERO_STATS
