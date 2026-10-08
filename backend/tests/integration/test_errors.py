import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.auth import AuthService

PASSWORD = "senha-que-nao-pode-vazar-123"
FAILURE_MESSAGE = "falha simulada"


def _json_events(output: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


def test_unexpected_error_returns_500_and_logs_error_internal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def failing_login(*args: object) -> None:
        raise RuntimeError(FAILURE_MESSAGE)

    monkeypatch.setattr(AuthService, "login", failing_login)

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/auth/login", json={"username": "qualquer_usuario", "password": PASSWORD}
        )

    output = capsys.readouterr().out
    errors = [event for event in _json_events(output) if event["type"] == "error.internal"]
    assert response.status_code == 500
    assert response.json() == {"detail": "Erro interno."}
    assert len(errors) == 1
    assert errors[0]["level"] == "ERROR"
    assert errors[0]["details"] == {
        "method": "POST",
        "route": "/api/auth/login",
        "exception": "RuntimeError",
    }
    assert "Traceback" in errors[0]["stack"]
    assert FAILURE_MESSAGE in errors[0]["stack"]
    assert PASSWORD not in output
