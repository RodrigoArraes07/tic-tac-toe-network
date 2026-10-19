import pytest

from app.core.config import Settings


def test_allowed_origins_are_read_as_a_comma_separated_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173, https://localhost")

    settings = Settings()

    assert settings.allowed_origins == ["http://localhost:5173", "https://localhost"]


def test_allowed_origins_drop_empty_items_and_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", " HTTPS://Localhost/ ,, ")

    settings = Settings()

    assert settings.allowed_origins == ["https://localhost"]
