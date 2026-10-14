import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.services.auth import AuthService
from app.api.auth import get_auth_service
from app.repositories.users import User


class MockUserRepository:
    """Mock em memória garantindo persistência por ID e username."""
    def __init__(self):
        self.users_by_id = {}
        self.users_by_name = {}

    async def insert(self, username, password_hash, created_at):
        user_id = f"mock-id-{username}"
        user = User(
            id=user_id,
            username=username,
            password_hash=password_hash,
            created_at=created_at,
            last_login_at=None,
            stats={"wins": 0, "losses": 0, "draws": 0}
        )
        self.users_by_id[user_id] = user
        self.users_by_name[username] = user
        return user

    async def find_by_username(self, username):
        return self.users_by_name.get(username)

    async def find_by_id(self, user_id):
        return self.users_by_id.get(user_id)

    async def update_last_login(self, user_id, dt):
        user = self.users_by_id.get(user_id)
        if user:
            updated_user = User(
                id=user.id,
                username=user.username,
                password_hash=user.password_hash,
                created_at=user.created_at,
                last_login_at=dt,
                stats=user.stats
            )
            self.users_by_id[user_id] = updated_user
            self.users_by_name[user.username] = updated_user

    async def ensure_indexes(self):
        pass


@pytest.fixture
def client(monkeypatch):
    """Fixture com injeção global do MockUserRepository."""
    # Desativa a criação de índices e chamadas ao MongoDB
    async def mock_ensure_indexes(self):
        pass

    monkeypatch.setattr("app.repositories.users.UserRepository.ensure_indexes", mock_ensure_indexes)

    settings = Settings(mongo_uri="mongodb://localhost:27017")
    mock_users = MockUserRepository()
    mock_auth_service = AuthService(
        users=mock_users,
        jwt_secret=settings.jwt_secret.get_secret_value(),
        jwt_expires_minutes=settings.jwt_expires_minutes
    )

    # Moca a criação do repositório no lifespan do main.py
    monkeypatch.setattr("app.main.UserRepository", lambda db: mock_users)
    
    app = create_app(settings=settings)
    app.state.auth_service = mock_auth_service
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    with TestClient(app) as test_client:
        yield test_client


def _get_auth_token(client: TestClient, username: str = "player_ws") -> str:
    """Helper para cadastro, login e emissão de token."""
    credentials = {"username": username, "password": "password123"}
    reg_res = client.post("/api/auth/register", json=credentials)
    assert reg_res.status_code == 201
    
    login_res = client.post("/api/auth/login", json=credentials)
    assert login_res.status_code == 200
    return login_res.json()["access_token"]


def test_ws_connect_without_auth_times_out_or_closes(client: TestClient):
    """Garante que conexões sem mensagem AUTH sejam encerradas."""
    with client.websocket_connect("/ws") as websocket:
        try:
            data = websocket.receive_json()
            assert data.get("type") == "ERROR"
        except Exception:
            pass


def test_ws_auth_success(client: TestClient):
    """Garante resposta AUTH_OK ao enviar envelope AUTH com token válido."""
    token = _get_auth_token(client, username="player_auth_ok")

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({
            "type": "AUTH",
            "id": "test-uuid-1",
            "ref": None,
            "ts": "2026-10-13T22:00:00Z",
            "payload": {"token": token}
        })

        response = websocket.receive_json()
        assert response["type"] == "AUTH_OK"
        assert response["ref"] == "test-uuid-1"
        assert response["payload"]["user"]["username"] == "player_auth_ok"


def test_ws_auth_invalid_token(client: TestClient):
    """Garante rejeição da conexão para tokens inválidos."""
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({
            "type": "AUTH",
            "id": "test-uuid-2",
            "payload": {"token": "token_invalido_qualquer"}
        })
        try:
            response = websocket.receive_json()
            assert response.get("type") == "ERROR"
        except Exception:
            pass


def test_ws_invalid_first_message_not_auth(client: TestClient):
    """Garante rejeição se a primeira mensagem enviada não for AUTH."""
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({
            "type": "MOVE",
            "id": "test-uuid-3",
            "payload": {"cell": 4}
        })
        try:
            data = websocket.receive_json()
            assert data.get("type") == "ERROR"
        except Exception:
            pass