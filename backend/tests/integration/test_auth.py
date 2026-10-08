from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pymongo.collection import Collection

from app.main import create_app

PASSWORD = "senha-correta-123"
WRONG_PASSWORD = "senha-errada-123"
MAX_FAILED_LOGINS = 5
ZERO_STATS = {"wins": 0, "losses": 0, "draws": 0, "points": 0}

type UsernameFactory = Callable[[], str]
type UsersCollection = Collection[dict[str, Any]]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def _register(client: TestClient, username: str, password: str = PASSWORD) -> Any:
    return client.post("/api/auth/register", json={"username": username, "password": password})


def _login(client: TestClient, username: str, password: str) -> Any:
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_t01_valid_registration_stores_an_argon2id_hash(
    client: TestClient, new_username: UsernameFactory, users_collection: UsersCollection
) -> None:
    username = new_username()

    response = _register(client, username.upper())

    assert response.status_code == 201
    assert response.json().keys() == {"id", "username"}
    assert response.json()["username"] == username
    document = users_collection.find_one({"username": username})
    assert document is not None
    assert document["password_hash"].startswith("$argon2id$")
    assert PASSWORD not in str(document)
    assert "password" not in document
    assert document["created_at"] is not None
    assert document["last_login_at"] is None
    assert document["stats"] == ZERO_STATS


def test_t02_registration_with_existing_username_returns_409(
    client: TestClient, new_username: UsernameFactory
) -> None:
    username = new_username()
    _register(client, username)

    same_case = _register(client, username)
    other_case = _register(client, username.upper())

    assert same_case.status_code == 409
    assert other_case.status_code == 409


def test_t03_wrong_password_and_unknown_user_get_the_same_401(
    client: TestClient, new_username: UsernameFactory
) -> None:
    username = new_username()
    _register(client, username)

    wrong_password = _login(client, username, WRONG_PASSWORD)
    unknown_user = _login(client, new_username(), PASSWORD)

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


def test_t04_sixth_wrong_attempt_in_a_minute_returns_429(
    client: TestClient, new_username: UsernameFactory
) -> None:
    username = new_username()
    _register(client, username)

    failures = [_login(client, username, WRONG_PASSWORD) for _ in range(MAX_FAILED_LOGINS)]
    sixth_attempt = _login(client, username, WRONG_PASSWORD)

    assert [response.status_code for response in failures] == [401] * MAX_FAILED_LOGINS
    assert sixth_attempt.status_code == 429


def test_login_returns_a_token_that_opens_me(
    client: TestClient, new_username: UsernameFactory, users_collection: UsersCollection
) -> None:
    username = new_username()
    user_id = _register(client, username).json()["id"]

    login = _login(client, username, PASSWORD)
    body = login.json()
    me = client.get("/api/me", headers={"Authorization": f"Bearer {body['access_token']}"})

    assert login.status_code == 200
    assert body.keys() == {"access_token", "token_type", "expires_in", "user"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["user"] == {"id": user_id, "username": username}
    assert me.status_code == 200
    assert me.json() == {"id": user_id, "username": username, "stats": ZERO_STATS}
    document = users_collection.find_one({"username": username})
    assert document is not None
    assert document["last_login_at"] is not None


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer token-invalido"}])
def test_me_without_a_valid_token_returns_401(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/api/me", headers=headers)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("ab", PASSWORD),
        ("a" * 21, PASSWORD),
        ("nome invalido", PASSWORD),
        ("usuario_valido", "curta"),
        ("usuario_valido", "s" * 73),
    ],
)
def test_registration_with_invalid_data_returns_422(
    client: TestClient, username: str, password: str
) -> None:
    response = _register(client, username, password)

    assert response.status_code == 422


def test_registration_rejects_non_string_fields(client: TestClient) -> None:
    payload = {"username": {"$ne": None}, "password": PASSWORD}

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 422
