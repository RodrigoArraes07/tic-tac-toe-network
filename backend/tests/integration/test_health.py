from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

UNREACHABLE_MONGO_URI = "mongodb://localhost:27999/?serverSelectionTimeoutMS=200"


def test_health_returns_ok_when_database_is_available() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_health_returns_degraded_when_database_is_unreachable() -> None:
    settings = Settings(mongo_uri=UNREACHABLE_MONGO_URI, mongo_db="jogo_da_velha")

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": "error"}
